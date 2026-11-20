"""Prepare a private browser-auth configuration draft without changing live settings."""

import json
import os
import re
import secrets

SECRET_KEYS = ("BROWSER_AUTH_CSRF_SECRET", "BROWSER_AUTH_SESSION_SECRET")


def make_draft(selected, checker, *, token_factory=secrets.token_urlsafe):
    settings = {
        key: selected.get(key) if isinstance(selected.get(key), str) else ""
        for key in checker["ENV_KEYS"]
    }
    settings.update(
        AUTH_MODE="token", ENABLE_DEV_ROUTES="false", BROWSER_AUTH_REGISTRATION_ENABLED="false"
    )
    generated = []
    for _key in SECRET_KEYS:
        for _attempt in range(16):
            token = token_factory(48)
            if (
                isinstance(token, str)
                and re.fullmatch(r"[A-Za-z0-9_-]{64}", token)
                and token not in generated
            ):
                generated.append(token)
                break
        else:
            raise ValueError("dedicated secret generation failed")
    settings.update(zip(SECRET_KEYS, generated, strict=True))
    return {
        "version": 1,
        "purpose": "browser_auth_configuration_draft",
        "settings": settings,
        "owner_identity_reviewed": False,
        "google_credentials_verified": False,
        "live_activation_ready": False,
    }


def safe_summary(document, checker):
    environment = checker["inspect_environment"](document["settings"])
    return {
        "draft_created": True,
        "environment_format": environment,
        "configuration_needed": {
            key: status for key, status in environment["checks"].items() if status != "format_ok"
        },
        "generated_secret_fields": list(SECRET_KEYS),
        "source_environment_modified": False,
        "owner_identity_reviewed": False,
        "google_credentials_verified": False,
        "live_activation_ready": False,
    }


def write_draft(path, document, checker):
    data = (json.dumps(document, indent=2, ensure_ascii=True) + "\n").encode("utf-8")
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    if path.read_bytes() != data:
        raise RuntimeError("private draft verification failed")
    result = safe_summary(document, checker)
    result["private_configuration_path"] = str(path)
    # No configuration bytes, credentials or configuration-file hash enter evidence.
    return result
