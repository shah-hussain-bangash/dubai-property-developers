"""Exercise supplied-source boundaries through authenticated HTTP for every agent."""

from contextlib import contextmanager

from fastapi.testclient import TestClient

from apps.api.app.main import create_app
from core.config.settings import AuthMode, Environment, Settings
from core.exceptions.errors import AuthenticationError
from core.security.rbac import Principal, Role
from knowledge.agent_data.catalogue import dataset_ids

BASE = "/api/v1/knowledge/agents"


class FixtureVerifier:
    async def verify(self, token):
        identities = {
            "a-manager": ("tenant-a", Role.SALES_MANAGER),
            "b-manager": ("tenant-b", Role.SALES_MANAGER),
            "a-viewer": ("tenant-a", Role.VIEWER),
        }
        if token not in identities:
            raise AuthenticationError("Unknown fictional identity")
        tenant, role = identities[token]
        return Principal(subject=token, tenant_id=tenant, roles=frozenset({role}))


def headers(identity="a-manager"):
    return {"Authorization": "Bearer " + identity}


@contextmanager
def workspace(path):
    app = create_app(
        Settings(
            _env_file=None,
            environment=Environment.TEST,
            auth_mode=AuthMode.TOKEN,
            agent_knowledge_path=str(path),
            rate_limit_per_minute=10000,
        )
    )
    app.state.token_verifier = FixtureVerifier()
    with TestClient(app) as client:
        yield client


def add(client, agent, text, identity="a-manager"):
    response = client.post(
        f"{BASE}/{agent}/sources",
        headers=headers(identity),
        json={"title": "Fictional boundary fixture", "kind": "text", "text": text},
    )
    assert response.status_code == 200, (agent, response.text)
    return response.json()["source"]["id"]


def test_all_agent_and_tenant_api_boundaries_survive_restart(tmp_path):
    agents = dataset_ids()
    path = tmp_path / "sources.sqlite3"
    sources = {}
    with workspace(path) as client:
        index = client.get(BASE, headers=headers()).json()
        assert index["configured"] and {a["id"] for a in index["agents"]} == set(agents)
        for tenant in ("a", "b"):
            for agent in agents:
                text = f"Fictional canary gardens belong exclusively to tenant {tenant}, agent {agent}."
                sources[tenant, agent] = (add(client, agent, text, f"{tenant}-manager"), text)

    # Recreate the app/runtime against the same private store, as on a service restart.
    with workspace(path) as client:
        for tenant in ("a", "b"):
            for agent in agents:
                own_id, text = sources[tenant, agent]
                auth = headers(f"{tenant}-manager")
                route = f"{BASE}/{agent}"
                listed = client.get(route + "/sources", headers=auth).json()["sources"]
                assert [s["id"] for s in listed] == [own_id], (tenant, agent)
                answer = client.post(
                    route + "/answer", headers=auth, json={"question": "fictional canary gardens"}
                ).json()
                assert answer["text"] == "[1] " + text, (tenant, agent, answer)
                assert answer["agent_id"] == agent and answer["supplied_sources_only"]
                assert answer["method"] == "source-excerpts" and answer["sent"] is False
                assert [s["source_id"] for s in answer["sources"]] == [own_id]
                missing = client.post(
                    route + "/answer", headers=auth, json={"question": "quasar telescope zoology"}
                ).json()
                assert missing["answered"] is False and missing["sources"] == []
                # Knowing any foreign source ID cannot authorize its deletion.
                foreign = [sources[tenant, other][0] for other in agents if other != agent]
                foreign.append(sources["b" if tenant == "a" else "a", agent][0])
                for source_id in foreign:
                    assert (
                        client.delete(route + "/sources/" + source_id, headers=auth).status_code
                        == 404
                    ), (tenant, agent, source_id)
        for tenant in ("a", "b"):
            for agent in agents:
                remaining = client.get(
                    f"{BASE}/{agent}/sources", headers=headers(f"{tenant}-manager")
                ).json()["sources"]
                assert [s["id"] for s in remaining] == [sources[tenant, agent][0]]


def test_identical_content_deletion_remains_scoped_to_one_owner(tmp_path):
    with workspace(tmp_path / "sources.sqlite3") as client:
        identifiers = {
            (tenant, agent): add(
                client, agent, "Fictional identical garden policy.", f"{tenant}-manager"
            )
            for tenant in ("a", "b")
            for agent in dataset_ids()
        }
        # IDs are content hashes: the tenant and agent predicates must still apply.
        assert len(set(identifiers.values())) == 1
        source_id = next(iter(identifiers.values()))
        assert (
            client.delete(f"{BASE}/documents/sources/{source_id}", headers=headers()).status_code
            == 200
        )
        for tenant, agent in identifiers:
            sources = client.get(
                f"{BASE}/{agent}/sources", headers=headers(f"{tenant}-manager")
            ).json()["sources"]
            assert len(sources) == (0 if (tenant, agent) == ("a", "documents") else 1)


def test_viewers_and_spoofed_identity_cannot_modify_any_agent(tmp_path):
    with workspace(tmp_path / "sources.sqlite3") as client:
        for agent in dataset_ids():
            route = f"{BASE}/{agent}"
            source_id = add(client, agent, "Fictional protected garden policy.")
            assert client.get(route + "/sources").status_code == 401
            spoofed = {**headers("a-viewer"), "X-Dev-Roles": "admin", "X-Tenant-ID": "tenant-b"}
            assert (
                client.post(
                    route + "/sources",
                    headers=spoofed,
                    json={"title": "Spoof", "kind": "text", "text": "Fictional spoofed policy."},
                ).status_code
                == 403
            )
            assert (
                client.delete(route + "/sources/" + source_id, headers=spoofed).status_code == 403
            )
            assert (
                client.post(
                    route + "/answer",
                    headers=headers(),
                    json={"question": "garden policy", "tenant_id": "tenant-b"},
                ).status_code
                == 422
            )
            assert (
                client.get(route + "/sources", headers=spoofed).json()["sources"][0]["id"]
                == source_id
            )
            assert (
                client.get(route + "/sources", headers=headers("b-manager")).json()["sources"] == []
            )
