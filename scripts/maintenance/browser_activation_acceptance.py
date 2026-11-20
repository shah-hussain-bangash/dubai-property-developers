"""Sanitized activation status and isolated real Redis OAuth-flow acceptance."""

import asyncio
import re
import secrets
from urllib.parse import urlsplit
from uuid import UUID


class ScopedRedis:
    """Translate only OAuth-flow keys into a fresh maintenance-only namespace."""

    def __init__(self, client):
        self.client = client
        self.prefix = "step546:" + secrets.token_hex(16) + ":"
        self.expected = {}

    def key(self, key):
        if re.fullmatch(r"account-auth:google:flow:[0-9a-f]{64}", key) is None:
            raise ValueError("unexpected flow key")
        return self.prefix + key

    async def set(self, key, value, *, nx, ex):
        if nx is not True or ex != 60:
            raise ValueError("unexpected acceptance reservation")
        key = self.key(key)
        self.expected[key] = value
        return await self.client.set(key, value, nx=True, ex=ex)

    async def eval(self, script, count, key, expected):
        if count != 1:
            raise ValueError("unexpected flow script scope")
        return await self.client.eval(script, 1, self.key(key), expected)


async def exercise_redis(redis_url, flow, *, factory=None):
    result = {
        "acceptance_status": "not_configured",
        "connection_attempted": False,
        "connection_established": False,
        "checks": {},
        "cleanup_confirmed": False,
        "real_redis_atomicity_tested": False,
        "live_activation_ready": False,
        "real_google_login_tested": False,
        "application_redis_keys_modified": False,
        "expiry_accelerated_for_test": True,
    }
    if not redis_url:
        return result
    try:
        parsed = urlsplit(redis_url)
        _port = parsed.port
        if (
            parsed.scheme not in {"redis", "rediss"}
            or not parsed.hostname
            or parsed.query
            or parsed.fragment
            or (parsed.path not in ("", "/") and re.fullmatch(r"/\d+", parsed.path) is None)
            or any(c.isspace() or ord(c) < 32 for c in redis_url)
        ):
            raise ValueError("unsupported Redis URL")
    except Exception:
        result["acceptance_status"] = "unsupported_configuration"
        return result
    client = scoped = None
    stage = "connect"
    try:
        if factory is None:
            from redis.asyncio import Redis

            factory = Redis.from_url
        result["connection_attempted"] = True
        client = factory(
            redis_url,
            decode_responses=False,
            socket_connect_timeout=3,
            socket_timeout=3,
            max_connections=32,
            retry_on_timeout=False,
        )
        scoped = ScopedRedis(client)
        result["checks"]["ping"] = await client.ping() is True
        result["connection_established"] = result["checks"]["ping"]
        if not result["connection_established"]:
            raise RuntimeError("Redis ping failed")
        stage = "flow_acceptance"
        store = flow["GoogleOAuthFlowStore"](scoped, ttl_seconds=60)
        org, other = UUID(int=5461), UUID(int=5462)
        state, binding = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        await store.reserve(state, org, binding)
        key, expected = next(iter(scoped.expected.items()))
        result["checks"]["reservation_ttl"] = 0 < await client.pttl(key) <= 60000
        raw = await client.get(key)
        result["checks"]["no_raw_state_or_binding"] = (
            state not in key
            and isinstance(raw, bytes)
            and state.encode() not in raw
            and binding.encode() not in raw
        )
        denied = False
        try:
            await store.reserve(state, org, binding)
        except flow["OAuthFlowError"]:
            denied = True
        result["checks"]["duplicate_reservation_denied"] = denied
        result["checks"]["foreign_browser_denied"] = (
            await store.consume(state, org, secrets.token_urlsafe(32)) is False
        )
        result["checks"]["foreign_organization_denied"] = (
            await store.consume(state, other, binding) is False
        )
        result["checks"]["foreign_attempts_preserve_record"] = (
            await client.get(key) == expected.encode()
        )
        consumed = await asyncio.gather(*(store.consume(state, org, binding) for _ in range(16)))
        result["checks"]["concurrent_single_winner"] = sum(value is True for value in consumed) == 1
        result["real_redis_atomicity_tested"] = True
        result["checks"]["consumed_key_absent"] = await client.exists(key) == 0
        result["checks"]["missing_flow_denied"] = (
            await store.consume(secrets.token_urlsafe(32), org, binding) is False
        )
        state2 = secrets.token_urlsafe(32)
        await store.reserve(state2, org, binding)
        second = list(scoped.expected)[-1]
        # Exercise real Redis expiry immediately without waiting a full minute.
        await client.pexpireat(second, 1)
        result["checks"]["expired_flow_denied"] = await store.consume(state2, org, binding) is False
        result["acceptance_status"] = "checks_completed"
    except Exception:
        result.update(acceptance_status="unavailable_or_failed", failure_stage=stage)
    finally:
        if client is not None:
            try:
                if scoped is not None:
                    for key, expected in scoped.expected.items():
                        await client.eval(flow["_CONSUME"], 1, key, expected)
                    result["cleanup_confirmed"] = all(
                        count == 0
                        for count in await asyncio.gather(
                            *(client.exists(key) for key in scoped.expected)
                        )
                    )
                if result["cleanup_confirmed"] is not True:
                    result["acceptance_status"] = "cleanup_not_confirmed"
                result["checks"]["owned_keys_cleaned"] = result["cleanup_confirmed"]
            except Exception:
                result["acceptance_status"] = "cleanup_not_confirmed"
            try:
                await client.aclose()
            except Exception:
                result["acceptance_status"] = "connection_cleanup_failed"
    if result["acceptance_status"] == "checks_completed":
        result["acceptance_status"] = (
            "passed_and_cleaned" if all(result["checks"].values()) else "checks_failed"
        )
    return result


def activation_status(environment, migrations, database, redis):
    blockers = []
    if environment.get("configuration_format_ready") is not True:
        blockers.append("browser_environment_incomplete")
    if migrations.get("required_migrations_registered") is not True:
        blockers.append("migration_sources_incomplete")
    if (
        database.get("inspection_status") != "completed"
        or database.get("metadata", {}).get("catalog_metadata_compatible") is not True
    ):
        blockers.append("database_schema_unverified")
    if redis.get("acceptance_status") != "passed_and_cleaned":
        blockers.append("redis_flow_acceptance_unverified")
    return {
        "infrastructure_checks_passed": not blockers,
        "blockers": blockers,
        "activation_remaining": [
            "owner_approval_and_identity_review",
            "real_google_oidc_login_acceptance",
            "explicit_browser_route_installation",
        ],
        "live_activation_ready": False,
        "live_registration_enabled": False,
    }
