"""Customer previews use only current, explicitly approved, own source passages."""

from datetime import date, timedelta

import pytest

from knowledge.agent_data.catalogue import dataset_ids
from tests.security.test_assigned_source_api_isolation import BASE, headers, workspace


@pytest.mark.parametrize("agent", dataset_ids())
def test_every_agent_customer_preview_respects_approval_ownership_and_expiry(
    tmp_path, monkeypatch, agent
):
    today = date.today()
    path = tmp_path / "sources.sqlite3"
    route = f"{BASE}/{agent}"
    with workspace(path) as client:

        def add(target, text, approved, identity="a-manager", review=None):
            response = client.post(
                f"{BASE}/{target}/sources",
                headers=headers(identity),
                json={
                    "kind": "text",
                    "title": "Fictional preview fixture",
                    "text": text,
                    "customer_safe": approved,
                    "review_by": review,
                },
            )
            assert response.status_code == 200
            return response.json()["source"]["id"]

        staff_id = add(agent, "Fictional previewmarker gardens contain staff-only details.", False)
        approved_id = add(
            agent,
            "Fictional previewmarker gardens allow two visits.",
            True,
            review=today.isoformat(),
        )
        other = next(a for a in dataset_ids() if a != agent)
        add(other, "Fictional previewmarker gardens belong to another agent.", True)
        add(
            agent,
            "Fictional previewmarker gardens belong to another organization.",
            True,
            "b-manager",
        )
        before = client.get(route + "/sources", headers=headers()).json()
        default = client.post(
            route + "/answer",
            headers=headers("a-viewer"),
            json={"question": "previewmarker gardens"},
        ).json()
        explicit = client.post(
            route + "/answer",
            headers=headers(),
            json={"question": "previewmarker gardens", "audience": "staff"},
        ).json()
        assert explicit == default and "audience" not in default  # Legacy staff contract.
        assert {s["source_id"] for s in default["sources"]} == {staff_id, approved_id}
        response = client.post(
            route + "/answer",
            headers=headers("a-viewer"),
            json={"question": "previewmarker gardens", "audience": "customer"},
        )
        assert response.status_code == 200 and "no-store" in response.headers["cache-control"]
        customer = response.json()
        assert customer["agent_id"] == agent and customer["audience"] == "customer"
        assert customer["supplied_sources_only"] is True and customer["sent"] is False
        assert [s["source_id"] for s in customer["sources"]] == [approved_id]
        assert "staff-only" not in customer["text"] and "another" not in customer["text"]
        assert client.get(route + "/sources", headers=headers()).json() == before
        assert (
            client.get(route + "/sources/" + approved_id + "/reviews", headers=headers()).json()[
                "events"
            ]
            == []
        )

    class Tomorrow(date):
        @classmethod
        def today(cls):
            return today + timedelta(days=1)

    monkeypatch.setattr("knowledge.assigned_sources.date", Tomorrow)
    with workspace(path) as client:
        customer = client.post(
            route + "/answer",
            headers=headers(),
            json={"question": "previewmarker gardens", "audience": "customer"},
        ).json()
        assert (
            customer["audience"] == "customer"
            and not customer["answered"]
            and not customer["sources"]
        )
        staff = client.post(
            route + "/answer", headers=headers(), json={"question": "previewmarker gardens"}
        ).json()
        assert [s["source_id"] for s in staff["sources"]] == [staff_id]
        # Renew without customer approval: staff regains the source, customers still abstain.
        response = client.patch(
            route + "/sources/" + approved_id + "/review",
            headers=headers(),
            json={"review_by": (today + timedelta(days=3)).isoformat(), "reviewed": True},
        )
        assert response.status_code == 200
        assert not client.post(
            route + "/answer",
            headers=headers(),
            json={"question": "previewmarker gardens", "audience": "customer"},
        ).json()["answered"]
        # Fresh explicit approval restores only this agent's matching passage.
        response = client.patch(
            route + "/sources/" + approved_id + "/review",
            headers=headers(),
            json={
                "review_by": (today + timedelta(days=3)).isoformat(),
                "reviewed": True,
                "customer_safe": True,
            },
        )
        assert response.status_code == 200
        restored = client.post(
            route + "/answer",
            headers=headers(),
            json={"question": "previewmarker gardens", "audience": "customer"},
        ).json()
        assert [s["source_id"] for s in restored["sources"]] == [approved_id]
        client.delete(route + "/sources/" + approved_id, headers=headers())
        assert not client.post(
            route + "/answer",
            headers=headers(),
            json={"question": "previewmarker gardens", "audience": "customer"},
        ).json()["answered"]


@pytest.mark.parametrize("audience", [None, True, "all", "Customer", "staff,customer", {}, []])
def test_invalid_preview_audiences_are_rejected(tmp_path, audience):
    with workspace(tmp_path / "sources.sqlite3") as client:
        response = client.post(
            f"{BASE}/documents/answer",
            headers=headers(),
            json={"question": "fictional gardens", "audience": audience},
        )
        assert response.status_code == 422


def test_customer_preview_requires_auth_and_registered_agent(tmp_path):
    with workspace(tmp_path / "sources.sqlite3") as client:
        body = {"question": "fictional gardens", "audience": "customer"}
        assert client.post(f"{BASE}/documents/answer", json=body).status_code == 401
        assert (
            client.post(f"{BASE}/unknown/answer", headers=headers(), json=body).status_code == 404
        )
