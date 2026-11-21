"""API rate-limit settings fail early for unusable request quotas."""

import pytest
from pydantic import ValidationError

from core.config.settings import Settings


@pytest.mark.parametrize("value", [0, -1])
def test_non_positive_api_request_quota_is_rejected(value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, rate_limit_per_minute=value)


@pytest.mark.parametrize("value", [1, 120])
def test_positive_api_request_quota_loads_from_environment(monkeypatch, value):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", str(value))
    assert Settings(_env_file=None).rate_limit_per_minute == value
