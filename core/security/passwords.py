"""Password hashing for optional local authentication (stdlib scrypt).

Format: ``scrypt$<n>$<r>$<p>$<salt_b64>$<hash_b64>``. N=2**14 is a baseline that
keeps tests fast; raise it (OWASP suggests N=2**17) for production. Parameters are
stored per hash, so existing hashes keep verifying after a change. Records use a
16-byte salt and a 64-byte digest; malformed records fail closed.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

_N, _R, _P, _DKLEN = 2**14, 8, 1, 64
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("password must be at least 12 characters")
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return "$".join(
        [
            "scrypt",
            str(_N),
            str(_R),
            str(_P),
            base64.b64encode(salt).decode(),
            base64.b64encode(digest).decode(),
        ]
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, hash_b64 = encoded.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64, validate=True)
        expected = base64.b64decode(hash_b64, validate=True)
        if len(salt) != _SALT_BYTES or len(expected) != _DKLEN:
            return False
        candidate = hashlib.scrypt(
            password.encode(), salt=salt, n=int(n), r=int(r), p=int(p), dklen=_DKLEN
        )
    except (ValueError, TypeError, OverflowError):
        return False
    return hmac.compare_digest(candidate, expected)
