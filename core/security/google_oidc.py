"""Google OIDC adapter awaiting application and account-store integration.

Only complete() returns an external identity, after Authlib callback processing.
This module never creates or approves users, links accounts by email, or issues
application sessions. Production composition must provide secure OAuth state
storage, middleware, trusted configuration, and internal identity mapping.
"""
import math
import secrets
import time
from collections.abc import Mapping
from urllib.parse import urlsplit

from authlib.integrations.starlette_client import OAuth
from email_validator import EmailNotValidError, validate_email

GOOGLE_METADATA = "https://accounts.google.com/.well-known/openid-configuration"
GOOGLE_ISSUER = "https://accounts.google.com"

class GoogleSignInError(Exception):
    pass

class GoogleOIDC:
    def __init__(
        self, *, client_id, client_secret, redirect_uri,
        allow_local_http=False,
    ):
        if not isinstance(client_id, str) or not client_id.strip():
            raise ValueError("Google client ID required")
        if not isinstance(client_secret, str) or not client_secret.strip():
            raise ValueError("Google client secret required")
        if type(allow_local_http) is not bool:
            raise ValueError("explicit local HTTP setting required")
        if not isinstance(redirect_uri, str):
            raise ValueError("trusted callback URL required")
        try:
            parsed = urlsplit(redirect_uri)
            port = parsed.port
        except ValueError:
            raise ValueError("invalid callback URL") from None
        local_http = (
            allow_local_http and parsed.scheme == "http"
            and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        )
        if (
            (parsed.scheme != "https" and not local_http)
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query or parsed.fragment
            or not parsed.path.startswith("/")
            or any(character.isspace() for character in redirect_uri)
        ):
            raise ValueError("trusted HTTPS callback URL required")
        self._client_id = client_id
        self._redirect_uri = redirect_uri
        oauth = OAuth()
        self._client = oauth.register(
            name="google",
            client_id=client_id,
            client_secret=client_secret,
            server_metadata_url=GOOGLE_METADATA,
            client_kwargs={
                "scope": "openid email profile",
                "code_challenge_method": "S256",
            },
        )

    def _require_session(self, request):
        if "session" not in request.scope:
            raise GoogleSignInError("Google sign-in is unavailable")

    async def start(self, request):
        self._require_session(request)
        return await self._client.authorize_redirect(
            request,
            self._redirect_uri,
            nonce=secrets.token_urlsafe(32),
        )

    async def complete(self, request):
        self._require_session(request)
        try:
            # Authlib must exchange the code and validate the OIDC token.
            # Never replace this with decoding a token supplied by the browser.
            token = await self._client.authorize_access_token(request)
            claims = token.get("userinfo")
            if not isinstance(claims, Mapping):
                raise ValueError("verified identity missing")
            if claims.get("iss") not in {
                GOOGLE_ISSUER, "accounts.google.com",
            }:
                raise ValueError("issuer mismatch")
            audience = claims.get("aud")
            if isinstance(audience, str):
                audiences = [audience]
            elif (
                isinstance(audience, list) and audience
                and all(isinstance(value, str) for value in audience)
            ):
                audiences = audience
            else:
                raise ValueError("audience missing")
            if self._client_id not in audiences:
                raise ValueError("audience mismatch")
            authorized_party = claims.get("azp")
            if (
                authorized_party is not None
                and authorized_party != self._client_id
            ) or (
                len(audiences) > 1 and authorized_party != self._client_id
            ):
                raise ValueError("authorized party mismatch")
            expires = claims.get("exp")
            if (
                type(expires) not in (int, float)
                or not math.isfinite(expires)
                or expires <= time.time()
            ):
                raise ValueError("expired identity")
            subject = claims.get("sub")
            if (
                not isinstance(subject, str) or not subject.strip()
                or len(subject) > 255
                or any(ord(character) < 32 or ord(character) == 127
                       for character in subject)
            ):
                raise ValueError("invalid subject")
            if claims.get("email_verified") is not True:
                raise ValueError("verified email required")
            email = validate_email(
                claims.get("email", ""),
                check_deliverability=False,
            ).normalized
            name = claims.get("name")
            if not isinstance(name, str) or not name.strip():
                name = email
            return {
                "issuer": GOOGLE_ISSUER,
                "subject": subject,
                "email": email,
                "full_name": name.strip()[:200],
            }
        except Exception:
            # Do not expose tokens, authorization codes, or provider errors.
            raise GoogleSignInError("Google sign-in could not be completed") from None
