"""Independent account credential candidate; held password module is untouched.

Uses the previously inspected generator's format and parameters. Historical
compatibility, numeric-policy approval, and live application review are separate.
"""
import base64
import hashlib
import hmac
import secrets

_N, _R, _P, _DKLEN = 16384, 8, 1, 64
_MAXMEM = 33554432

def _password_bytes(password):
    if not isinstance(password, str) or len(password) > 1024:
        raise ValueError("invalid password")
    try:
        data = password.encode("utf-8")
    except UnicodeError:
        raise ValueError("invalid password") from None
    if len(data) > 4096:
        raise ValueError("invalid password")
    return data

def _canonical_base64(value, encoded_length, decoded_length):
    if len(value) != encoded_length:
        raise ValueError("invalid encoded field")
    data = base64.b64decode(value, validate=True)
    if (
        len(data) != decoded_length
        or base64.b64encode(data).decode("ascii") != value
    ):
        raise ValueError("invalid encoded field")
    return data

def hash_password(password):
    data = _password_bytes(password)
    if len(password) < 12:
        raise ValueError("password must contain at least 12 characters")
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(
        data, salt=salt, n=_N, r=_R, p=_P,
        dklen=_DKLEN, maxmem=_MAXMEM,
    )
    return "$".join([
        "scrypt", "16384", "8", "1",
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(key).decode("ascii"),
    ])

def verify_password(password, encoded):
    try:
        data = _password_bytes(password)
        if not isinstance(encoded, str) or len(encoded) > 256:
            return False
        fields = encoded.split("$")
        if len(fields) != 6 or fields[:4] != ["scrypt", "16384", "8", "1"]:
            return False
        salt = _canonical_base64(fields[4], 24, 16)
        expected = _canonical_base64(fields[5], 88, 64)
        candidate = hashlib.scrypt(
            data, salt=salt, n=_N, r=_R, p=_P,
            dklen=_DKLEN, maxmem=_MAXMEM,
        )
    except (ValueError, TypeError, OverflowError, UnicodeError):
        return False
    return hmac.compare_digest(candidate, expected)
