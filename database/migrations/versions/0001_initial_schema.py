"""Initial schema: identity, CRM, property catalog, conversations, agents, workflows,
integrations, governance and knowledge (pgvector).

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-10-08
"""

from collections.abc import Sequence
import sqlalchemy as sa
from sqlalchemy.schema import SchemaItem
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql


revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIMENSION = 1536
JSONB = postgresql.JSONB()


def _pk(table: str) -> list[SchemaItem]:
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=f"pk_{table}"),
    ]


def _org(table: str) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        "organization_id",
        sa.Uuid(),
        sa.ForeignKey(
            "organizations.id", ondelete="RESTRICT", name=f"fk_{table}_organization_id_organizations"
        ),
        nullable=False,
    )


def _timestamps() -> list[sa.Column]:  # type: ignore[type-arg]
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def _fk(table: str, column: str, target: str, ondelete: str) -> sa.Column:  # type: ignore[type-arg]
    ref_table = target.split(".")[0]
    return sa.Column(
        column,
        sa.Uuid(),
        sa.ForeignKey(target, ondelete=ondelete, name=f"fk_{table}_{column}_{ref_table}"),
        nullable=True,
    )


def _json(name: str, empty: str = "{}") -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(name, JSONB, nullable=False, server_default=sa.text(f"'{empty}'::jsonb"))


def _org_index(table: str) -> None:
    op.create_index(f"ix_{table}_organization_id", table, ["organization_id"])


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ------------------------------------------------------------------ identity
    op.create_table(
        "organizations",
        *_pk("organizations"),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )
    op.create_table(
        "roles",
        *_pk("roles"),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("description", sa.String(255)),
        *_timestamps(),
        sa.UniqueConstraint("name", name="uq_roles_name"),
    )
    op.create_table(
        "users",
        *_pk("users"),
        _org("users"),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("password_hash", sa.String(255)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.UniqueConstraint("organization_id", "email", name="uq_users_organization_id_email"),
    )
    _org_index("users")
    op.create_table(
        "user_roles",
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_user_roles_user_id_users"),
            nullable=False,
        ),
        sa.Column(
            "role_id",
            sa.Uuid(),
            sa.ForeignKey("roles.id", ondelete="CASCADE", name="fk_user_roles_role_id_roles"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_id", "role_id", name="pk_user_roles"),
    )

    # ------------------------------------------------------------------ CRM core
    op.create_table(
        "contacts",
        *_pk("contacts"),
        _org("contacts"),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(254)),
        sa.Column("phone_e164", sa.String(20)),
        sa.Column("preferred_language", sa.String(8)),
        sa.Column("consent_marketing", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("consent_whatsapp", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("consent_updated_at", sa.DateTime(timezone=True)),
        sa.Column("crm_external_id", sa.String(64)),
        *_timestamps(),
    )
    _org_index("contacts")
    op.create_index("ix_contacts_org_email", "contacts", ["organization_id", "email"])
    op.create_index("ix_contacts_org_phone", "contacts", ["organization_id", "phone_e164"])

    op.create_table(
        "leads",
        *_pk("leads"),
        _org("leads"),
        _fk("leads", "contact_id", "contacts.id", "SET NULL"),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="new"),
        sa.Column("purpose", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(254)),
        sa.Column("phone_e164", sa.String(20)),
        sa.Column("message", sa.Text()),
        sa.Column("budget_min_aed", sa.Numeric(14, 2)),
        sa.Column("budget_max_aed", sa.Numeric(14, 2)),
        _json("preferred_locations", "[]"),
        _json("property_types", "[]"),
        sa.Column("bedrooms", sa.Integer()),
        sa.Column("timeline_months", sa.Integer()),
        sa.Column("score", sa.Integer()),
        sa.Column("qualification_category", sa.String(32)),
        _json("score_factors"),
        _fk("leads", "assigned_to_user_id", "users.id", "SET NULL"),
        sa.Column("external_ref", sa.String(120)),
        sa.Column("crm_external_id", sa.String(64)),
        sa.Column("dedupe_key", sa.String(128)),
        _fk("leads", "duplicate_of_id", "leads.id", "SET NULL"),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        *_timestamps(),
        sa.UniqueConstraint(
            "organization_id", "source", "external_ref", name="uq_leads_organization_id_source_external_ref"
        ),
        sa.CheckConstraint("score IS NULL OR (score >= 0 AND score <= 100)", name="ck_leads_score_range"),
    )
    _org_index("leads")
    op.create_index("ix_leads_org_status", "leads", ["organization_id", "status"])
    op.create_index("ix_leads_org_dedupe", "leads", ["organization_id", "dedupe_key"])
    op.create_index("ix_leads_org_received", "leads", ["organization_id", "received_at"])

    # ------------------------------------------------------------------ property catalog
    op.create_table(
        "projects",
        *_pk("projects"),
        _org("projects"),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("developer_name", sa.String(200), nullable=False),
        sa.Column("community", sa.String(120), nullable=False),
        sa.Column("city", sa.String(80), nullable=False, server_default="Dubai"),
        sa.Column("completion_status", sa.String(32), nullable=False),
        sa.Column("handover_quarter", sa.String(16)),
        sa.Column("description", sa.Text()),
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("data_source", sa.String(64), nullable=False),
        sa.Column("data_as_of", sa.Date()),
        *_timestamps(),
        sa.UniqueConstraint(
            "organization_id", "developer_name", "name", name="uq_projects_organization_id_developer_name_name"
        ),
    )
    _org_index("projects")
    op.create_index("ix_projects_community", "projects", ["community"])

    op.create_table(
        "properties",
        *_pk("properties"),
        _org("properties"),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE", name="fk_properties_project_id_projects"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("property_type", sa.String(32), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("project_id", "name", name="uq_properties_project_id_name"),
    )
    _org_index("properties")
    op.create_index("ix_properties_project_id", "properties", ["project_id"])

    op.create_table(
        "payment_plans",
        *_pk("payment_plans"),
        _org("payment_plans"),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE", name="fk_payment_plans_project_id_projects"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("down_payment_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("during_construction_pct", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("on_handover_pct", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("post_handover_pct", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("post_handover_months", sa.Integer()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
        sa.UniqueConstraint("project_id", "name", name="uq_payment_plans_project_id_name"),
        sa.CheckConstraint(
            "down_payment_pct + during_construction_pct + on_handover_pct + post_handover_pct = 100",
            name="ck_payment_plans_percentages_sum_100",
        ),
    )
    _org_index("payment_plans")
    op.create_index("ix_payment_plans_project_id", "payment_plans", ["project_id"])

    op.create_table(
        "property_units",
        *_pk("property_units"),
        _org("property_units"),
        sa.Column(
            "property_id",
            sa.Uuid(),
            sa.ForeignKey("properties.id", ondelete="CASCADE", name="fk_property_units_property_id_properties"),
            nullable=False,
        ),
        _fk("property_units", "payment_plan_id", "payment_plans.id", "SET NULL"),
        sa.Column("unit_ref", sa.String(64), nullable=False),
        sa.Column("bedrooms", sa.Integer(), nullable=False),
        sa.Column("size_sqft", sa.Numeric(10, 2)),
        sa.Column("price_aed", sa.Numeric(14, 2)),
        sa.Column("availability", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("data_as_of", sa.Date()),
        *_timestamps(),
        sa.UniqueConstraint("property_id", "unit_ref", name="uq_property_units_property_id_unit_ref"),
    )
    _org_index("property_units")
    op.create_index("ix_property_units_property_id", "property_units", ["property_id"])
    op.create_index(
        "ix_property_units_org_avail_price", "property_units", ["organization_id", "availability", "price_aed"]
    )

    op.create_table(
        "opportunities",
        *_pk("opportunities"),
        _org("opportunities"),
        _fk("opportunities", "lead_id", "leads.id", "SET NULL"),
        _fk("opportunities", "contact_id", "contacts.id", "SET NULL"),
        _fk("opportunities", "unit_id", "property_units.id", "SET NULL"),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False, server_default="discovery"),
        sa.Column("expected_value_aed", sa.Numeric(14, 2)),
        _fk("opportunities", "owner_user_id", "users.id", "SET NULL"),
        sa.Column("crm_external_id", sa.String(64)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        *_timestamps(),
    )
    _org_index("opportunities")
    op.create_index("ix_opportunities_org_stage", "opportunities", ["organization_id", "stage"])

    op.create_table(
        "tasks",
        *_pk("tasks"),
        _org("tasks"),
        _fk("tasks", "lead_id", "leads.id", "CASCADE"),
        _fk("tasks", "contact_id", "contacts.id", "CASCADE"),
        _fk("tasks", "opportunity_id", "opportunities.id", "CASCADE"),
        sa.Column("task_type", sa.String(32), nullable=False, server_default="follow_up"),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        _fk("tasks", "assigned_to_user_id", "users.id", "SET NULL"),
        sa.Column("assigned_agent_key", sa.String(64)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        *_timestamps(),
    )
    _org_index("tasks")
    op.create_index("ix_tasks_org_status_due", "tasks", ["organization_id", "status", "due_at"])

    # ------------------------------------------------------------------ governance
    op.create_table(
        "approval_requests",
        *_pk("approval_requests"),
        _org("approval_requests"),
        sa.Column("tool_name", sa.String(64), nullable=False),
        sa.Column("action_category", sa.String(32), nullable=False),
        sa.Column("requested_by", sa.String(128), nullable=False),
        sa.Column("requested_by_agent", sa.String(64)),
        sa.Column("reason", sa.Text(), nullable=False),
        _json("payload"),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("correlation_id", sa.String(64)),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        _fk("approval_requests", "decided_by_user_id", "users.id", "SET NULL"),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decision_note", sa.Text()),
        *_timestamps(),
        sa.UniqueConstraint("idempotency_key", name="uq_approval_requests_idempotency_key"),
    )
    _org_index("approval_requests")
    op.create_index("ix_approval_requests_org_status", "approval_requests", ["organization_id", "status"])

    op.create_table(
        "audit_logs",
        *_pk("audit_logs"),
        _org("audit_logs"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(128)),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("correlation_id", sa.String(64)),
        _json("details"),
    )
    _org_index("audit_logs")
    op.create_index("ix_audit_logs_org_occurred", "audit_logs", ["organization_id", "occurred_at"])
    op.create_index("ix_audit_logs_resource", "audit_logs", ["resource_type", "resource_id"])
    op.create_index("ix_audit_logs_correlation_id", "audit_logs", ["correlation_id"])

    # ------------------------------------------------------------------ conversations
    op.create_table(
        "conversations",
        *_pk("conversations"),
        _org("conversations"),
        _fk("conversations", "contact_id", "contacts.id", "SET NULL"),
        _fk("conversations", "lead_id", "leads.id", "SET NULL"),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("external_thread_id", sa.String(128)),
        sa.Column("last_inbound_at", sa.DateTime(timezone=True)),
        _fk("conversations", "assigned_user_id", "users.id", "SET NULL"),
        _json("state"),
        *_timestamps(),
        sa.UniqueConstraint(
            "organization_id",
            "channel",
            "external_thread_id",
            name="uq_conversations_organization_id_channel_external_thread_id",
        ),
    )
    _org_index("conversations")
    op.create_index("ix_conversations_org_status", "conversations", ["organization_id", "status"])

    op.create_table(
        "messages",
        *_pk("messages"),
        _org("messages"),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey(
                "conversations.id", ondelete="CASCADE", name="fk_messages_conversation_id_conversations"
            ),
            nullable=False,
        ),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("sender_type", sa.String(32), nullable=False),
        sa.Column("sender_ref", sa.String(128)),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("language", sa.String(8)),
        sa.Column("external_message_id", sa.String(128)),
        sa.Column("delivery_status", sa.String(32), nullable=False, server_default="draft"),
        _fk("messages", "approval_request_id", "approval_requests.id", "SET NULL"),
        _json("attributes"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        *_timestamps(),
        sa.UniqueConstraint(
            "organization_id",
            "channel",
            "external_message_id",
            name="uq_messages_organization_id_channel_external_message_id",
        ),
    )
    _org_index("messages")
    op.create_index("ix_messages_conversation_sent", "messages", ["conversation_id", "sent_at"])

    # ------------------------------------------------------------------ agents & workflows
    op.create_table(
        "ai_agents",
        *_pk("ai_agents"),
        sa.Column("agent_key", sa.String(64), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("implementation_status", sa.String(32), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        _json("config"),
        *_timestamps(),
        sa.UniqueConstraint("agent_key", name="uq_ai_agents_agent_key"),
    )

    op.create_table(
        "workflow_executions",
        *_pk("workflow_executions"),
        _org("workflow_executions"),
        sa.Column("workflow_key", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128)),
        sa.Column("current_step", sa.String(64)),
        _json("state"),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_message", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.UniqueConstraint("idempotency_key", name="uq_workflow_executions_idempotency_key"),
    )
    _org_index("workflow_executions")
    op.create_index("ix_workflow_executions_workflow_key", "workflow_executions", ["workflow_key"])
    op.create_index("ix_workflow_executions_correlation_id", "workflow_executions", ["correlation_id"])
    op.create_index(
        "ix_workflow_executions_org_status", "workflow_executions", ["organization_id", "status"]
    )

    op.create_table(
        "agent_executions",
        *_pk("agent_executions"),
        _org("agent_executions"),
        sa.Column(
            "agent_key",
            sa.String(64),
            sa.ForeignKey(
                "ai_agents.agent_key", ondelete="RESTRICT", name="fk_agent_executions_agent_key_ai_agents"
            ),
            nullable=False,
        ),
        _fk("agent_executions", "workflow_execution_id", "workflow_executions.id", "SET NULL"),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        _json("input_summary"),
        _json("output_summary"),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_message", sa.Text()),
        sa.Column("model", sa.String(64)),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_estimate", sa.Numeric(12, 6)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("duration_ms", sa.Integer()),
        *_timestamps(),
    )
    _org_index("agent_executions")
    op.create_index("ix_agent_executions_correlation_id", "agent_executions", ["correlation_id"])
    op.create_index(
        "ix_agent_executions_workflow_execution_id", "agent_executions", ["workflow_execution_id"]
    )
    op.create_index("ix_agent_executions_agent_started", "agent_executions", ["agent_key", "started_at"])

    # ------------------------------------------------------------------ integrations
    op.create_table(
        "integration_connections",
        *_pk("integration_connections"),
        _org("integration_connections"),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False, server_default="mock"),
        sa.Column("status", sa.String(32), nullable=False, server_default="not_configured"),
        _json("config"),
        sa.Column("secret_ref", sa.String(200)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        *_timestamps(),
        sa.UniqueConstraint(
            "organization_id", "provider", name="uq_integration_connections_organization_id_provider"
        ),
    )
    _org_index("integration_connections")

    op.create_table(
        "external_sync_records",
        *_pk("external_sync_records"),
        _org("external_sync_records"),
        sa.Column(
            "connection_id",
            sa.Uuid(),
            sa.ForeignKey(
                "integration_connections.id",
                ondelete="CASCADE",
                name="fk_external_sync_records_connection_id_integration_connections",
            ),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("local_id", sa.Uuid()),
        sa.Column("external_id", sa.String(128), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("source_version", sa.String(64)),
        sa.Column("payload_hash", sa.String(64)),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
        sa.Column("error", sa.Text()),
        *_timestamps(),
        sa.UniqueConstraint(
            "connection_id",
            "entity_type",
            "external_id",
            name="uq_external_sync_records_connection_id_entity_type_external_id",
        ),
    )
    _org_index("external_sync_records")
    op.create_index("ix_external_sync_records_local_id", "external_sync_records", ["local_id"])

    # ------------------------------------------------------------------ knowledge / RAG
    op.create_table(
        "knowledge_documents",
        *_pk("knowledge_documents"),
        _org("knowledge_documents"),
        sa.Column("document_key", sa.String(128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("source_uri", sa.String(500)),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("access_level", sa.String(32), nullable=False, server_default="internal"),
        _json("allowed_roles", "[]"),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("effective_date", sa.Date()),
        sa.Column("review_by", sa.Date()),
        _json("attributes"),
        *_timestamps(),
        sa.UniqueConstraint(
            "organization_id",
            "document_key",
            "version",
            name="uq_knowledge_documents_organization_id_document_key_version",
        ),
    )
    _org_index("knowledge_documents")
    op.create_index("ix_knowledge_documents_document_key", "knowledge_documents", ["document_key"])

    op.create_table(
        "knowledge_chunks",
        *_pk("knowledge_chunks"),
        _org("knowledge_chunks"),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey(
                "knowledge_documents.id",
                ondelete="CASCADE",
                name="fk_knowledge_chunks_document_id_knowledge_documents",
            ),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        _json("attributes"),
        *_timestamps(),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_knowledge_chunks_document_id_chunk_index"),
    )
    _org_index("knowledge_chunks")
    op.create_index("ix_knowledge_chunks_document_id", "knowledge_chunks", ["document_id"])

    op.create_table(
        "chunk_embeddings",
        *_pk("chunk_embeddings"),
        sa.Column(
            "chunk_id",
            sa.Uuid(),
            sa.ForeignKey(
                "knowledge_chunks.id", ondelete="CASCADE", name="fk_chunk_embeddings_chunk_id_knowledge_chunks"
            ),
            nullable=False,
        ),
        sa.Column("embedding_model", sa.String(100), nullable=False),
        sa.Column("dimension", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIMENSION), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "chunk_id", "embedding_model", name="uq_chunk_embeddings_chunk_id_embedding_model"
        ),
    )
    op.create_index("ix_chunk_embeddings_chunk_id", "chunk_embeddings", ["chunk_id"])
    op.execute(
        "CREATE INDEX ix_chunk_embeddings_embedding_hnsw ON chunk_embeddings "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    # Reverse dependency order. The ``vector`` extension is left installed on purpose
    # because other schemas may rely on it.
    for table in (
        "chunk_embeddings",
        "knowledge_chunks",
        "knowledge_documents",
        "external_sync_records",
        "integration_connections",
        "agent_executions",
        "workflow_executions",
        "ai_agents",
        "messages",
        "conversations",
        "audit_logs",
        "approval_requests",
        "tasks",
        "opportunities",
        "property_units",
        "payment_plans",
        "properties",
        "projects",
        "leads",
        "contacts",
        "user_roles",
        "users",
        "roles",
        "organizations",
    ):
        op.drop_table(table)
