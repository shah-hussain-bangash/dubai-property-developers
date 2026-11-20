"""Environment-based configuration.

All values are read from environment variables (optionally a local ``.env``
file, which is git-ignored).

Secrets use ``SecretStr`` so they are never printed in reprs or logs.
No production credentials are defined here.

Persistence backends can be configured independently:
- LEAD_STORE_BACKEND: memory or postgres
- WORKFLOW_STORE_BACKEND: memory or postgres
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import (
    BaseSettings,
    NoDecode,
    SettingsConfigDict,
)


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class AuthMode(StrEnum):
    # Development principal injected without credentials.
    # Refused outside development/test.
    DEV = "dev"

    # Bearer tokens validated by a configured TokenVerifier.
    TOKEN = "token"  # noqa: S105 -- Protocol/enum label; this literal is not a credential.


class LeadStoreBackend(StrEnum):
    """Available lead-storage implementations."""

    MEMORY = "memory"
    POSTGRES = "postgres"


class WorkflowStoreBackend(StrEnum):
    """Available workflow-history storage implementations."""

    MEMORY = "memory"
    POSTGRES = "postgres"


def _split_csv(value: object) -> object:
    """Split comma-separated environment values into a list."""

    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]

    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- application -------------------------------------------------------
    app_name: str = "Dubai Real Estate AI Platform"
    app_version: str = "0.1.0"

    environment: Environment = Environment.DEVELOPMENT

    log_level: str = "INFO"
    log_json: bool = True

    default_timezone: str = "Asia/Dubai"
    default_tenant_id: str = "demo-org"

    # --- API ---------------------------------------------------------------
    api_host: str = "0.0.0.0"  # noqa: S104
    api_port: int = 8000

    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    enable_dev_routes: bool = True
    rate_limit_per_minute: int = 120

    # --- security ----------------------------------------------------------
    auth_mode: AuthMode = AuthMode.DEV

    secret_key: SecretStr = SecretStr("change-me-local-development-only")

    webhook_signing_secret: SecretStr | None = None
    webhook_tolerance_seconds: int = 300

    pii_redaction_enabled: bool = True

    # --- persistence -------------------------------------------------------
    database_url: SecretStr = SecretStr(
        "postgresql+asyncpg://dubai_ai:dubai_ai_local@localhost:5432/dubai_ai"
    )

    database_echo: bool = False

    database_pool_size: int = Field(
        default=5,
        ge=1,
    )

    redis_url: SecretStr = SecretStr("redis://localhost:6379/0")

    readiness_checks_required: bool = False

    # --- lead storage backend ---------------------------------------------
    #
    # Environment variable:
    # LEAD_STORE_BACKEND
    #
    # memory:
    #   In-memory lead storage for tests and local demos.
    #
    # postgres:
    #   Persistent lead storage using PostgresLeadStore.
    #
    # The backend is selected by workflows/runtime.py.

    lead_store_backend: LeadStoreBackend = LeadStoreBackend.MEMORY

    # --- workflow history storage backend ---------------------------------
    #
    # Environment variable:
    # WORKFLOW_STORE_BACKEND
    #
    # memory:
    #   Store workflow execution history in memory.
    #
    # postgres:
    #   Store workflow execution history in PostgreSQL
    #   using PostgresWorkflowRunStore.
    #
    # The runtime integration is configured separately.
    #
    # Keep MEMORY as the default to preserve existing
    # tests and application behavior until deployment.

    workflow_store_backend: WorkflowStoreBackend = WorkflowStoreBackend.MEMORY

    # --- LLM ---------------------------------------------------------------
    # Mock is the default; OpenAI requires explicit provider, model and key settings.

    llm_provider: str = "mock"
    prospect_storage_enabled: bool = False
    prospect_search_provider: Literal["disabled", "serpapi"] = "disabled"
    prospect_search_api_key: SecretStr | None = None
    prospect_search_daily_limit: int = Field(default=1, ge=1, le=10)
    local_ai_enabled: bool = False
    local_ai_connection: Literal["native", "docker-desktop"] = "native"

    llm_primary_model: str = "mock-deterministic"

    llm_fallback_models: Annotated[list[str], NoDecode] = Field(default_factory=list)

    llm_timeout_seconds: float = 30.0
    llm_max_retries: int = 2

    llm_api_key: SecretStr | None = None

    # --- embeddings / knowledge -------------------------------------------
    embedding_provider: str = "hashing"
    embedding_dimension: int = 1536

    knowledge_chunk_size: int = 800
    knowledge_chunk_overlap: int = 120
    knowledge_stale_after_days: int = 180

    # --- agents & governance ----------------------------------------------
    agent_default_timeout_seconds: float = 20.0

    approval_required_for_outbound_messages: bool = True
    approval_required_for_crm_writes: bool = False
    approval_required_for_calendar_events: bool = True

    data_retention_days_conversations: int = 365
    data_retention_days_audit_logs: int = 2555

    # --- integrations ------------------------------------------------------
    # All integration adapters default to mock mode.

    integrations_mode: str = "mock"

    espocrm_base_url: str | None = None
    espocrm_api_key: SecretStr | None = None

    meta_whatsapp_phone_number_id: str | None = None
    meta_whatsapp_access_token: SecretStr | None = None
    meta_graph_api_version: str = "v20.0"
    meta_app_secret: SecretStr | None = None

    google_credentials_file: str | None = None
    telephony_provider: str | None = None

    n8n_webhook_base_url: str | None = None
    slack_webhook_url: SecretStr | None = None

    # --- validators --------------------------------------------------------
    _split_origins = field_validator(
        "cors_allowed_origins",
        mode="before",
    )(_split_csv)

    _split_models = field_validator(
        "llm_fallback_models",
        mode="before",
    )(_split_csv)

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION

    @property
    def is_dev_like(self) -> bool:
        return self.environment in {
            Environment.DEVELOPMENT,
            Environment.TEST,
        }

    def validate_for_runtime(self) -> list[str]:
        """Return fatal configuration problems."""

        problems: list[str] = []

        if not self.is_dev_like:
            if self.auth_mode == AuthMode.DEV:
                problems.append("AUTH_MODE=dev is not allowed outside development/test")

            if self.enable_dev_routes:
                problems.append("ENABLE_DEV_ROUTES must be false outside development/test")

            if self.secret_key.get_secret_value().startswith("change-me"):
                problems.append("SECRET_KEY must be set to a strong unique value")

            if "*" in self.cors_allowed_origins:
                problems.append("CORS wildcard origin is not allowed outside development")

        return problems


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
