"""One-use Google OAuth flow records using an injected async Redis client.

No client or network connection is created here. Application composition must
supply an appropriately configured Redis client. Authlib must still validate
OAuth state, PKCE, nonce, and the Google ID token.
"""
import hashlib
import re
from uuid import UUID

_CONSUME = """
local value = redis.call('GET', KEYS[1])
if value == ARGV[1] then
    redis.call('DEL', KEYS[1])
    return 1
end
return 0
"""

class OAuthFlowError(Exception):
    pass

class GoogleOAuthFlowStore:
    def __init__(self, redis_client, *, ttl_seconds=600):
        if (
            not callable(getattr(redis_client, "set", None))
            or not callable(getattr(redis_client, "eval", None))
        ):
            raise ValueError("async Redis client required")
        if type(ttl_seconds) is not int or not 60 <= ttl_seconds <= 600:
            raise ValueError("flow lifetime must be 60 to 600 seconds")
        self._redis = redis_client
        self._ttl = ttl_seconds

    def _record(self, state, organization_id, browser_binding):
        if (
            not isinstance(state, str)
            or re.fullmatch(r"[A-Za-z0-9_-]{16,256}", state) is None
            or not isinstance(organization_id, UUID)
            or organization_id.int == 0
            or not isinstance(browser_binding, str)
            or re.fullmatch(r"[A-Za-z0-9_-]{43}", browser_binding) is None
        ):
            raise OAuthFlowError("invalid Google sign-in flow")
        state_digest = hashlib.sha256(state.encode("ascii")).hexdigest()
        binding_digest = hashlib.sha256(browser_binding.encode("ascii")).hexdigest()
        key = "account-auth:google:flow:" + state_digest
        value = str(organization_id) + "|" + binding_digest
        return key, value

    async def reserve(self, state, organization_id, browser_binding):
        key, value = self._record(state, organization_id, browser_binding)
        try:
            saved = await self._redis.set(key, value, nx=True, ex=self._ttl)
        except Exception:
            raise OAuthFlowError("Google sign-in storage unavailable") from None
        if saved is not True:
            raise OAuthFlowError("Google sign-in flow could not be reserved")

    async def consume(self, state, organization_id, browser_binding):
        key, value = self._record(state, organization_id, browser_binding)
        try:
            result = await self._redis.eval(_CONSUME, 1, key, value)
        except Exception:
            raise OAuthFlowError("Google sign-in storage unavailable") from None
        return result == 1
