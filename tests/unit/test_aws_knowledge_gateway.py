"""New knowledge authority cannot grant writes to the legacy AWS API."""

from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from apps.api.app.aws_knowledge_gateway import build_gateway
from apps.api.app.main import create_app
from core.config.settings import AuthMode, Environment, Settings
from core.exceptions.errors import AuthenticationError
from core.security.rbac import Principal, Role


class ReadVerifier:
    async def verify(self, token):
        if token != "fictional-check":
            raise AuthenticationError("bad token")
        return Principal(
            subject="existing-reader", tenant_id="existing-tenant", roles=frozenset({Role.VIEWER})
        )


def test_knowledge_scope_preserves_auth_tenant_and_all_other_write_denials(tmp_path):
    settings = Settings(
        _env_file=None,
        environment=Environment.TEST,
        auth_mode=AuthMode.TOKEN,
        agent_knowledge_path=str(tmp_path / "sources.sqlite3"),
    )
    legacy = create_app(settings)
    legacy.state.token_verifier = ReadVerifier()

    @legacy.middleware("http")
    async def read_only(request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            return JSONResponse({"error": "read only"}, status_code=403)
        return await call_next(request)

    headers = {"Authorization": "Bearer fictional-check"}
    with TestClient(build_gateway(legacy)) as client:
        path = "/api/v1/knowledge/agents/documents"
        assert client.get(path + "/sources").status_code == 401
        assert (
            client.get(path + "/sources", headers={"Authorization": "Bearer wrong"}).status_code
            == 401
        )
        result = client.post(
            path + "/sources",
            headers=headers,
            json={
                "title": "Fictional source",
                "kind": "text",
                "text": "Fictional gardens total eight.",
            },
        )
        assert result.status_code == 200, result.text
        assert client.post(
            path + "/answer", headers=headers, json={"question": "fictional gardens"}
        ).json()["answered"]
        assert (
            client.post("/api/v1/leads/demo-process", headers=headers, json={}).status_code == 403
        )
        assert (
            client.post("/api/v1/workflows/demo-run", headers=headers, json={}).status_code == 403
        )
        assert client.get("/api/v1/agents", headers=headers).status_code == 200
        assert legacy.state.token_verifier.__class__ is ReadVerifier
        assert legacy.state.runtime.assigned_sources.list_sources("other-tenant", "documents") == []
