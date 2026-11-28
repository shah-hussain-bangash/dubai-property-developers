"""Every agent keeps PDF, Markdown and imported website evidence through restart."""

import io
from urllib.parse import urlsplit

from reportlab.pdfgen.canvas import Canvas

from knowledge.agent_data.catalogue import dataset_ids
from knowledge.ingestion import assigned_inputs
from tests.security.test_assigned_source_api_isolation import BASE, headers, workspace


def pdf_fixture(marker):
    output = io.BytesIO()
    canvas = Canvas(output)
    canvas.drawString(40, 750, f"Fictional {marker} covermarker cover page.")
    canvas.showPage()
    canvas.drawString(40, 750, f"Fictional {marker} pdfmarker policy allows three visits.")
    canvas.showPage()
    canvas.save()
    return output.getvalue()


def mock_websites(monkeypatch, pages):
    requested = []

    class Response:
        status = 200

        def __init__(self, data):
            self.data = io.BytesIO(data)

        def getheader(self, name, default=None):
            return {"Content-Type": "text/html", "Content-Encoding": "identity"}.get(name, default)

        def read1(self, size):
            return self.data.read(size)

    class Connection:
        def __init__(self, host, address):
            self.path = None

        def request(self, method, path, headers):
            assert method == "GET"
            self.path = path
            requested.append(path)

        def getresponse(self):
            return Response(pages[self.path])

        def close(self):
            pass

    # Network and DNS are fixtures; the real fetch/read/decode/HTML pipeline runs.
    monkeypatch.setattr(
        assigned_inputs,
        "public_target",
        lambda url: ("example.test", "203.0.113.1", urlsplit(url).path),
    )
    monkeypatch.setattr(assigned_inputs, "PinnedHTTPS", Connection)
    return requested


def test_all_agents_keep_three_source_formats_scoped_through_restart(tmp_path, monkeypatch):
    agents = dataset_ids()
    assert len(agents) == 13
    markers = {agent: f"canary{index}" for index, agent in enumerate(agents)}
    pages = {
        f"/{agent}": (
            f"<p>Fictional {marker} webmarker policy allows two visits.</p>"
            f"<div hidden>Fictional {marker} unpublishedmarker policy requires ninety percent.</div>"
        ).encode()
        for agent, marker in markers.items()
    }
    requested = mock_websites(monkeypatch, pages)
    path = tmp_path / "sources.sqlite3"
    sources = {}
    with workspace(path) as client:
        for agent, marker in markers.items():
            route = f"{BASE}/{agent}/sources"
            uploaded = client.post(
                route,
                headers={**headers(), "Content-Type": "application/pdf"},
                params={"title": f"Fictional {agent} PDF"},
                content=pdf_fixture(marker),
            )
            assert uploaded.status_code == 200, (agent, uploaded.text)
            sources[agent, "pdfmarker"] = uploaded.json()["source"]["id"]
            markdown = client.post(
                route,
                headers={**headers(), "Content-Type": "text/markdown"},
                params={"title": f"Fictional {agent} Markdown"},
                content=f"Fictional {marker} markdownmarker policy allows four visits.".encode(),
            )
            assert markdown.status_code == 200, (agent, markdown.text)
            sources[agent, "markdownmarker"] = markdown.json()["source"]["id"]
            website = client.post(
                route,
                headers=headers(),
                json={
                    "title": f"Fictional {agent} website",
                    "kind": "website",
                    "url": f"https://example.test/{agent}",
                },
            )
            assert website.status_code == 200, (agent, website.text)
            sources[agent, "webmarker"] = website.json()["source"]["id"]
    assert set(requested) == set(pages) and len(requested) == 13

    with workspace(path) as client:
        for agent, marker in markers.items():
            route = f"{BASE}/{agent}"
            listed = client.get(route + "/sources", headers=headers()).json()["sources"]
            assert {s["id"] for s in listed} == {
                sources[agent, kind] for kind in ("pdfmarker", "markdownmarker", "webmarker")
            }
            assert {s["kind"] for s in listed} == {"pdf", "markdown", "website"}
            assert (
                client.get(route + "/sources", headers=headers("b-manager")).json()["sources"] == []
            )
            for kind, visits in (
                ("pdfmarker", "three"),
                ("markdownmarker", "four"),
                ("webmarker", "two"),
            ):
                question = f"{marker} {kind}"
                answer = client.post(
                    route + "/answer", headers=headers(), json={"question": question}
                ).json()
                assert answer["answered"] and answer["supplied_sources_only"] and not answer["sent"]
                assert (
                    answer["text"]
                    == f"[1] Fictional {marker} {kind} policy allows {visits} visits."
                )
                assert [s["source_id"] for s in answer["sources"]] == [sources[agent, kind]]
                assert answer["sources"][0]["page"] == (2 if kind == "pdfmarker" else None)
                for other in agents:
                    if other != agent:
                        foreign = client.post(
                            f"{BASE}/{other}/answer", headers=headers(), json={"question": question}
                        ).json()
                        assert not foreign["answered"] and foreign["sources"] == []
                tenant = client.post(
                    route + "/answer", headers=headers("b-manager"), json={"question": question}
                ).json()
                assert not tenant["answered"] and tenant["sources"] == []
            hidden = client.post(
                route + "/answer",
                headers=headers(),
                json={"question": f"{marker} unpublishedmarker"},
            ).json()
            assert not hidden["answered"] and hidden["sources"] == []

        for index, agent in enumerate(agents):
            foreign_agent = agents[(index + 1) % len(agents)]
            for kind in ("pdfmarker", "markdownmarker", "webmarker"):
                source_id = sources[agent, kind]
                assert (
                    client.delete(
                        f"{BASE}/{foreign_agent}/sources/{source_id}", headers=headers()
                    ).status_code
                    == 404
                )
                assert (
                    client.delete(
                        f"{BASE}/{agent}/sources/{source_id}", headers=headers()
                    ).status_code
                    == 200
                )
            assert client.get(f"{BASE}/{agent}/sources", headers=headers()).json()["sources"] == []
            deleted = client.post(
                f"{BASE}/{agent}/answer",
                headers=headers(),
                json={"question": f"{markers[agent]} pdfmarker"},
            ).json()
            assert not deleted["answered"] and deleted["sources"] == []
