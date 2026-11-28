"""Review history uses trusted actors and the same source ownership boundaries."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from core.exceptions.errors import DomainValidationError
from knowledge.agent_data.catalogue import dataset_ids
from knowledge.assigned_sources import AssignedSources
from tests.security.test_assigned_source_api_isolation import BASE, add, headers, workspace

TEXT = "Fictional history gardens allow two visits."


@pytest.mark.parametrize("agent", dataset_ids())
def test_all_agent_history_uses_trusted_actor_and_survives_restart(tmp_path, agent):
    path = tmp_path / "sources.sqlite3"
    review = (date.today() + timedelta(days=3)).isoformat()
    with workspace(path) as client:
        source_id = add(client, agent, TEXT)
        assert add(client, agent, TEXT, "b-manager") == source_id
        route = f"{BASE}/{agent}/sources/{source_id}"
        assert client.get(route + "/reviews", headers=headers()).json()["events"] == []
        body = {"review_by": review, "reviewed": True, "customer_safe": True}
        assert client.patch(route + "/review", headers=headers(), json=body).status_code == 200
        response = client.get(route + "/reviews", headers=headers("a-viewer"))
        assert response.status_code == 200 and "no-store" in response.headers["cache-control"]
        own = response.json()
        assert own["agent_id"] == agent and own["source_id"] == source_id
        assert own["has_more"] is False and own["next_cursor"] is None
        assert len(own["events"]) == 1
        event = own["events"][0]
        assert event["reviewed_by"] == "a-manager"
        assert datetime.fromisoformat(event["reviewed_at"]).utcoffset() == UTC.utcoffset(None)
        assert event["previous_review_by"] is None and event["review_by"] == review
        assert event["previous_customer_safe"] is False and event["customer_safe"] is True
        assert client.get(route + "/reviews", headers=headers("b-manager")).json()["events"] == []
        other = next(a for a in dataset_ids() if a != agent)
        assert (
            client.get(f"{BASE}/{other}/sources/{source_id}/reviews", headers=headers()).status_code
            == 404
        )
        assert (
            client.patch(route + "/review", headers=headers("a-viewer"), json=body).status_code
            == 403
        )
        assert (
            client.patch(
                route + "/review", headers=headers(), json={**body, "reviewed_by": "forged"}
            ).status_code
            == 422
        )
        assert (
            client.patch(
                route + "/review", headers=headers(), json={**body, "reviewed": False}
            ).status_code
            == 422
        )
        assert client.get(route + "/reviews", headers=headers()).json() == own
        client.patch(route + "/review", headers=headers("b-manager"), json=body)
        foreign_event = client.get(route + "/reviews", headers=headers("b-manager")).json()[
            "events"
        ][0]
        assert foreign_event["reviewed_by"] == "b-manager"
        assert (
            client.get(
                route + "/reviews",
                params={"before_event": foreign_event["event_id"]},
                headers=headers(),
            ).status_code
            == 404
        )
    with workspace(path) as client:
        assert client.get(route + "/reviews", headers=headers()).json() == own


def test_history_pages_have_no_gaps_and_source_deletion_removes_only_own_history(tmp_path):
    with workspace(tmp_path / "sources.sqlite3") as client:
        source_id = add(client, "documents", TEXT)
        add(client, "documents", TEXT, "b-manager")
        other_id = add(client, "documents", "Fictional alternate review source.")
        route = f"{BASE}/documents/sources/{source_id}"
        expected_dates = []
        for index in range(43):
            review = (date.today() + timedelta(days=index + 1)).isoformat()
            expected_dates.append(review)
            response = client.patch(
                route + "/review", headers=headers(), json={"review_by": review, "reviewed": True}
            )
            assert response.status_code == 200
        all_events = []
        cursor = None
        sizes = []
        while True:
            page = client.get(
                route + "/reviews",
                params={} if cursor is None else {"before_event": cursor},
                headers=headers(),
            ).json()
            sizes.append(len(page["events"]))
            all_events.extend(page["events"])
            if not page["has_more"]:
                assert page["next_cursor"] is None
                break
            cursor = page["next_cursor"]
            assert cursor == page["events"][-1]["event_id"]
        assert sizes == [20, 20, 3]
        assert len({event["event_id"] for event in all_events}) == 43
        assert [event["review_by"] for event in all_events] == expected_dates[::-1]
        assert all_events[0]["previous_review_by"] == expected_dates[-2]
        assert (
            client.get(
                f"{BASE}/documents/sources/{other_id}/reviews",
                params={"before_event": all_events[0]["event_id"]},
                headers=headers(),
            ).status_code
            == 404
        )
        client.patch(
            route + "/review",
            headers=headers("b-manager"),
            json={"review_by": expected_dates[0], "reviewed": True},
        )
        assert client.delete(route, headers=headers()).status_code == 200
        assert client.get(route + "/reviews", headers=headers()).status_code == 404
        assert add(client, "documents", TEXT) == source_id
        assert client.get(route + "/reviews", headers=headers()).json()["events"] == []
        assert (
            len(client.get(route + "/reviews", headers=headers("b-manager")).json()["events"]) == 1
        )


def test_append_failure_rolls_back_source_metadata_and_allows_retry(tmp_path):
    path = tmp_path / "sources.sqlite3"
    store = AssignedSources(str(path))
    source = store.add("owner", "documents", "Fictional source", "text", [TEXT])
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TRIGGER reject_review BEFORE INSERT ON agent_source_reviews BEGIN SELECT RAISE(ABORT,'Fictional history failure'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="Fictional history failure"):
        store.review_source(
            "owner", "documents", source["id"], date.today(), True, "fixture-reviewer"
        )
    assert store.read_source("owner", "documents", source["id"])["source"] == source
    assert store.review_history("owner", "documents", source["id"])["events"] == []
    with sqlite3.connect(path) as db:
        db.execute("DROP TRIGGER reject_review")
    store.review_source("owner", "documents", source["id"], date.today(), True, "fixture-reviewer")
    assert len(store.review_history("owner", "documents", source["id"])["events"]) == 1


def test_concurrent_reviews_keep_a_complete_before_after_chain(tmp_path):
    store = AssignedSources(str(tmp_path / "sources.sqlite3"))
    source = store.add("owner", "documents", "Fictional source", "text", [TEXT])

    def review(index):
        return store.review_source(
            "owner",
            "documents",
            source["id"],
            date.today() + timedelta(days=index),
            bool(index % 2),
            f"fixture-reviewer-{index}",
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert len(list(pool.map(review, range(12)))) == 12
    events = store.review_history("owner", "documents", source["id"])["events"]
    assert len(events) == 12 and len({event["event_id"] for event in events}) == 12
    previous_date, previous_approval = None, False
    for event in reversed(events):
        assert event["previous_review_by"] == previous_date
        assert event["previous_customer_safe"] is previous_approval
        previous_date, previous_approval = event["review_by"], event["customer_safe"]
    current = store.read_source("owner", "documents", source["id"])["source"]
    assert current == {
        **source,
        "review_by": previous_date,
        "customer_safe": int(previous_approval),
    }


@pytest.mark.parametrize("actor", ["", "  ", "x" * 501, "line\nbreak"])
def test_invalid_internal_actor_does_not_update_source(tmp_path, actor):
    store = AssignedSources(str(tmp_path / "sources.sqlite3"))
    source = store.add("owner", "documents", "Fictional source", "text", [TEXT])
    with pytest.raises(DomainValidationError):
        store.review_source("owner", "documents", source["id"], date.today(), True, actor)
    assert store.read_source("owner", "documents", source["id"])["source"] == source


def test_existing_database_adds_empty_history_without_changing_source(tmp_path):
    path = tmp_path / "sources.sqlite3"
    store = AssignedSources(str(path))
    source = store.add("owner", "documents", "Fictional source", "text", [TEXT])
    with sqlite3.connect(path) as db:
        db.execute("DROP TABLE agent_source_reviews")
    old_source = store.read_source("owner", "documents", source["id"])
    assert old_source["source"] == source
    assert store.review_history("owner", "documents", source["id"])["events"] == []


def test_history_requires_auth_and_valid_scoped_cursor(tmp_path):
    with workspace(tmp_path / "sources.sqlite3") as client:
        source_id = add(client, "documents", TEXT)
        route = f"{BASE}/documents/sources/{source_id}/reviews"
        assert client.get(route).status_code == 401
        assert (
            client.get(route, params={"before_event": "bad"}, headers=headers()).status_code == 422
        )
        assert (
            client.get(route, params={"before_event": str(uuid4())}, headers=headers()).status_code
            == 404
        )
        assert (
            client.get(f"{BASE}/documents/sources/missing/reviews", headers=headers()).status_code
            == 404
        )
