"""Canonical request fingerprints for durable execution claims.

Experimental utility. No production ToolGateway integration.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def make_request_fingerprint(
    tenant_id: str,
    tool_name: str,
    payload: dict[str, Any],
) -> str:
    """Return SHA-256 over tenant, tool and canonical JSON payload."""

    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ValueError("tenant_id is required")

    if not isinstance(tool_name, str) or not tool_name.strip():
        raise ValueError("tool_name is required")

    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")

    try:
        canonical = json.dumps(
            {
                "tenant_id": tenant_id,
                "tool_name": tool_name,
                "payload": payload,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Request payload must contain only valid JSON values") from exc

    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
