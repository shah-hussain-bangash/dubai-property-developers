"""Validate locally supplied draft edits without granting activation."""

import copy
import json

EDITABLE = (
    "BROWSER_AUTH_TRUSTED_ORIGIN",
    "BROWSER_AUTH_ORGANIZATION_ID",
    "BROWSER_AUTH_OWNER_ID",
    "GOOGLE_OAUTH_CLIENT_ID",
    "GOOGLE_OAUTH_CLIENT_SECRET",
)
FIELDS = {
    "version",
    "purpose",
    "settings",
    "owner_identity_reviewed",
    "google_credentials_verified",
    "live_activation_ready",
}


def decode_private(data):
    if not isinstance(data, bytes) or len(data) > 131072:
        raise ValueError("Invalid private input")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate private field")
            result[key] = value
        return result

    try:
        return json.loads(data.decode("utf-8-sig"), object_pairs_hook=unique)
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError("Invalid private input") from None


def update_draft(document, edits, checker):
    if not isinstance(document, dict) or set(document) != FIELDS:
        raise ValueError("Invalid draft schema")
    if type(document["version"]) is not int or document["version"] != 1:
        raise ValueError("Unsupported draft version")
    if document["purpose"] != "browser_auth_configuration_draft":
        raise ValueError("Unsupported draft purpose")
    if any(
        type(document[key]) is not bool
        for key in (
            "owner_identity_reviewed",
            "google_credentials_verified",
            "live_activation_ready",
        )
    ):
        raise ValueError("Invalid review flags")
    settings = document["settings"]
    if not isinstance(settings, dict) or set(settings) != set(checker["ENV_KEYS"]):
        raise ValueError("Invalid draft settings")
    if not isinstance(edits, dict) or set(edits) - set(EDITABLE):
        raise ValueError("Unsupported editable field")
    for value in [*settings.values(), *edits.values()]:
        if (
            not isinstance(value, str)
            or len(value) > 4096
            or any(ord(c) < 32 or ord(c) == 127 for c in value)
        ):
            raise ValueError("Invalid configuration value")
    result = copy.deepcopy(document)
    for key, value in edits.items():
        if value:
            result["settings"][key] = value
    result["settings"].update(
        AUTH_MODE="token", ENABLE_DEV_ROUTES="false", BROWSER_AUTH_REGISTRATION_ENABLED="false"
    )
    for key in ("owner_identity_reviewed", "google_credentials_verified", "live_activation_ready"):
        result[key] = False
    return result
