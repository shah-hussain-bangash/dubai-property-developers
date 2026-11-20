"""Share isolated service fixtures with recovery scenarios in adjacent modules."""

from tests.integration.test_guarded_recovery_real_redis import environment as environment
from tests.integration.test_postgres_recovery_lease_store import recovery_setup as recovery_setup
from tests.integration.test_redis_recovery_evidence import (
    redis_recovery_setup as redis_recovery_setup,
)
