"""Uploaded file deadlines have the same scoped lifecycle as JSON source dates."""

from datetime import date

import pytest

from knowledge.agent_data.catalogue import dataset_ids
from tests.security.test_agent_source_format_journey import pdf_fixture
from tests.security.test_assigned_source_api_isolation import BASE, add, headers, workspace

TEXT = "Fictional datemarker pdfmarker policy allows three visits."


@pytest.mark.parametrize("agent", dataset_ids())
@pytest.mark.parametrize("mime", ["application/pdf", "text/plain", "text/markdown"])
def test_all_agent_file_deadlines_expire_persist_and_require_explicit_renewal(
    tmp_path, monkeypatch, agent, mime
):
    class Clock(date):
        day = date(2030, 1, 2)

        @classmethod
        def today(cls):
            return cls.day

    monkeypatch.setattr("knowledge.assigned_sources.date", Clock)
    path = tmp_path / "sources.sqlite3"
    route = f"{BASE}/{agent}"
    payload = pdf_fixture("datemarker") if mime == "application/pdf" else TEXT.encode()
    upload_headers = {**headers(), "Content-Type": mime}
    with workspace(path) as client:
        added = client.post(
            route + "/sources",
            params={"review_by": "2030-01-02", "customer_safe": "true"},
            content=payload,
            headers=upload_headers,
        )
        assert added.status_code == 200, added.text
        source_id = added.json()["source"]["id"]
        assert added.json()["source"]["review_by"] == "2030-01-02"
        assert added.json()["source"]["customer_safe"] == 1
        assert client.post(
            route + "/answer", json={"question": "datemarker pdfmarker"}, headers=headers()
        ).json()["answered"]  # Valid through the review day, including PDFs' second page.
        add(client, agent, TEXT, "b-manager")

    Clock.day = date(2030, 1, 3)
    with workspace(path) as client:

        def answer(identity="a-manager"):
            return client.post(
                route + "/answer",
                json={"question": "datemarker pdfmarker"},
                headers=headers(identity),
            ).json()

        assert answer()["answered"] is False
        evaluated = client.post(
            route + "/evaluate",
            json={
                "agent_id": agent,
                "cases": [
                    {
                        "id": "expired",
                        "question": "datemarker pdfmarker",
                        "expectation": "no_answer",
                    }
                ],
            },
            headers=headers(),
        )
        assert evaluated.status_code == 200 and evaluated.json()["passed"] == 1
        assert answer("b-manager")["answered"] is True
        listed = client.get(route + "/sources", headers=headers()).json()["sources"]
        assert [s["id"] for s in listed] == [source_id]
        assert listed[0]["review_by"] == "2030-01-02"
        unchanged = client.post(route + "/sources", content=payload, headers=upload_headers)
        assert unchanged.status_code == 200
        assert unchanged.json()["source"]["review_by"] == "2030-01-02"
        assert answer()["answered"] is False
        renewed = client.post(
            route + "/sources",
            params={"review_by": "2030-01-04"},
            content=payload,
            headers=upload_headers,
        )
        assert renewed.status_code == 200
        assert renewed.json()["source"]["id"] == source_id
        assert renewed.json()["source"]["review_by"] == "2030-01-04"
        assert renewed.json()["source"]["customer_safe"] == 0
        assert answer()["answered"] is True


@pytest.mark.parametrize(
    "value",
    [
        "bad",
        "2030-02-30",
        "20300102",
        "2030-W01-1",
        "1893456000",
        " 2030-01-02",
        "2030-01-02T00:00:00Z",
        "2000-01-01",
    ],
)
def test_bad_or_past_upload_dates_rejected_without_saving(tmp_path, value):
    with workspace(tmp_path / "sources.sqlite3") as client:
        route = f"{BASE}/documents/sources"
        response = client.post(
            route,
            params={"review_by": value},
            content=TEXT.encode(),
            headers={**headers(), "Content-Type": "text/plain"},
        )
        assert response.status_code == 422, response.text
        assert client.get(route, headers=headers()).json()["sources"] == []


@pytest.mark.parametrize("value", [None, ""])
def test_undated_upload_compatibility(tmp_path, value):
    with workspace(tmp_path / "sources.sqlite3") as client:
        response = client.post(
            f"{BASE}/documents/sources",
            params={} if value is None else {"review_by": value},
            content=TEXT.encode(),
            headers={**headers(), "Content-Type": "text/plain"},
        )
        assert response.status_code == 200
        assert response.json()["source"]["review_by"] is None
