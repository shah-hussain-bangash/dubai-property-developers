from __future__ import annotations

import pytest

from core.config.settings import AuthMode, Environment, Settings
from core.security.passwords import hash_password, verify_password
from core.security.rbac import Permission, Principal, Role
from core.security.redaction import REDACTED, redact_text, redact_value
from core.security.sanitization import sanitize_name, sanitize_text


def test_settings_parse_csv_origins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://a.test, http://b.test")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.cors_allowed_origins == ["http://a.test", "http://b.test"]


def test_settings_secrets_not_in_repr() -> None:
    s = Settings(_env_file=None, secret_key="super-secret-value-123")  # type: ignore[call-arg]
    assert "super-secret-value-123" not in repr(s)


def test_production_rejects_unsafe_defaults() -> None:
    s = Settings(_env_file=None, environment=Environment.PRODUCTION)  # type: ignore[call-arg]
    problems = s.validate_for_runtime()
    assert any("AUTH_MODE" in p for p in problems)
    assert any("ENABLE_DEV_ROUTES" in p for p in problems)
    assert any("SECRET_KEY" in p for p in problems)


def test_production_accepts_hardened_config() -> None:
    s = Settings(  # type: ignore[call-arg]
        _env_file=None,
        environment=Environment.PRODUCTION,
        auth_mode=AuthMode.TOKEN,
        enable_dev_routes=False,
        secret_key="a-strong-unique-production-secret",
        cors_allowed_origins="https://dashboard.example.com",
    )
    assert s.validate_for_runtime() == []


def test_redacts_secrets_and_masks_pii() -> None:
    text = "token Bearer abcdefghijklmnop email demo.user@example.com phone +971 50 000 0001"
    out = redact_text(text)
    assert "abcdefghijklmnop" not in out
    assert "demo.user@example.com" not in out
    assert "d***@example.com" in out
    assert "***001" in out


def test_redaction_keeps_dates_and_amounts() -> None:
    text = "on 2026-10-08 budget 1500000 AED"
    assert redact_text(text) == text


def test_redact_value_sensitive_keys_and_db_url() -> None:
    data = {"api_key": "xyz", "nested": {"password": "p"}, "url": "postgresql+asyncpg://u:pw@h/db"}
    out = redact_value(data)
    assert out["api_key"] == REDACTED
    assert out["nested"]["password"] == REDACTED
    assert "pw@" not in out["url"]


def test_password_hashing_roundtrip() -> None:
    encoded = hash_password("correct horse battery")
    assert encoded.startswith("scrypt$")
    assert verify_password("correct horse battery", encoded)
    assert not verify_password("wrong password!!", encoded)
    assert not verify_password("x", "garbage")


def test_password_minimum_length() -> None:
    with pytest.raises(ValueError):
        hash_password("short")


def test_rbac_least_privilege() -> None:
    viewer = Principal(subject="v", tenant_id="t", roles=frozenset({Role.VIEWER}))
    system = Principal(subject="s", tenant_id="t", roles=frozenset({Role.SYSTEM}))
    assert viewer.has(Permission.LEADS_READ)
    assert not viewer.has(Permission.LEADS_WRITE)
    assert not system.has(Permission.MESSAGES_SEND)  # automation cannot message customers directly
    assert Principal(subject="a", tenant_id="t", roles=frozenset({Role.ADMIN})).has(
        Permission.SETTINGS_ADMIN
    )


def test_sanitization_strips_control_and_bidi() -> None:
    assert sanitize_text("hi\x00 there‮!") == "hi there!"
    assert sanitize_name("<script>Ali</script>") == "scriptAli/script"
