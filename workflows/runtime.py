"""Composition root for the Dubai Real Estate AI Platform.

Wires:
    settings -> integrations -> tools -> knowledge -> agents -> workflows

Shared by the FastAPI application and background worker.

Lead storage is configurable:
    memory   - InMemoryLeadStore for demos and unit tests
    postgres - PostgresLeadStore for persistent lead records

Workflow execution history is configurable:
    memory   - InMemoryWorkflowRunStore
    postgres - PostgresWorkflowRunStore

When either PostgreSQL backend is selected, the runtime creates
one shared SQLAlchemy AsyncEngine and session factory.

Other foundation stores remain in-memory until their persistent
implementations are ready.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncEngine

from agents.base.context import (
    AgentDependencies,
    InMemoryExecutionRecorder,
)
from agents.registry import AgentRegistry
from core.config.settings import (
    LeadStoreBackend,
    Settings,
    WorkflowStoreBackend,
)
from core.events.audit import InMemoryAuditSink
from core.events.bus import InMemoryEventBus
from core.llm.factory import build_model_router
from core.memory.base import InMemoryConversationMemory
from core.observability.logging import get_logger
from core.observability.tracing import build_tracer
from core.policies.actions import ApprovalPolicy
from core.policies.approvals import InMemoryApprovalStore
from core.resilience.idempotency import InMemoryIdempotencyStore
from database.repositories.postgres_lead_store import (
    PostgresLeadStore,
)
from database.repositories.postgres_workflow_run_store import (
    PostgresWorkflowRunStore,
)
from database.sessions.engine import (
    create_engine,
    create_session_factory,
)
from integrations.factory import (
    IntegrationSet,
    build_integrations,
)
from knowledge.agent_data.catalogue import agent_documents
from knowledge.assigned_sources import AssignedSources
from knowledge.documents.demo_corpus import demo_documents
from knowledge.embeddings.base import HashingEmbeddingProvider
from knowledge.ingestion.pipeline import IngestionPipeline
from knowledge.retrieval.retriever import Retriever
from knowledge.vectorstores.base import InMemoryVectorStore
from tools.analytics.tools import (
    LeadScoringTool,
    SalesAnalyticsTool,
)
from tools.base import ToolGateway, ToolRegistry
from tools.calendar.tools import CalendarCreateEventTool
from tools.crm.tools import (
    CRMAddNoteTool,
    CRMCreateLeadTool,
    CRMFindLeadsTool,
    CRMUpdateLeadTool,
)
from tools.documents.tools import DocumentSearchTool
from tools.email.sender import MockEmailSender
from tools.email.tools import (
    EmailRenderTemplateTool,
    EmailSendTool,
)
from tools.property.catalog import InMemoryPropertyCatalog
from tools.property.tools import (
    PropertyMatchTool,
    PropertySearchTool,
)
from tools.search.lead_store import (
    InMemoryLeadStore,
    LeadStore,
)
from tools.search.tools import (
    LeadDuplicateSearchTool,
    LeadSaveTool,
)
from tools.whatsapp.tools import WhatsAppSendTool
from workflows.engine.core import (
    InMemoryWorkflowRunStore,
    WorkflowRunner,
)

logger = get_logger(__name__)


@dataclass
class PlatformRuntime:
    """Shared application runtime for API and worker processes."""

    settings: Settings
    integrations: IntegrationSet
    tools: ToolRegistry
    gateway: ToolGateway
    deps: AgentDependencies
    agents: AgentRegistry
    runner: WorkflowRunner

    # Lead storage can use memory or PostgreSQL.
    lead_store: LeadStore

    ingestion: IngestionPipeline
    retriever: Retriever
    audit: InMemoryAuditSink
    approvals: InMemoryApprovalStore
    email_sender: MockEmailSender
    assigned_sources: AssignedSources | None = None

    # Shared runtime-owned PostgreSQL engine.
    # None when both storage backends use memory.
    _db_engine: AsyncEngine | None = field(
        default=None,
        repr=False,
    )

    _initialized: bool = field(
        default=False,
        repr=False,
    )

    async def initialize(self) -> None:
        """Initialize resources and fictional development knowledge."""

        if self._initialized:
            return

        if self.settings.is_dev_like and self.assigned_sources is None:
            for doc in [
                *demo_documents(self.settings.default_tenant_id),
                *agent_documents(self.settings.default_tenant_id),
            ]:
                await self.ingestion.ingest(doc)

            logger.info("demo knowledge corpus ingested (fictional)")

        self._initialized = True

    async def shutdown(self) -> None:
        """Release resources owned by this runtime."""

        try:
            await self.integrations.aclose()
        finally:
            try:
                if self._db_engine is not None:
                    await self._db_engine.dispose()
                    self._db_engine = None
            finally:
                self._initialized = False

        logger.info("platform runtime shut down")


def build_runtime(settings: Settings) -> PlatformRuntime:
    """Build the application's tools, agents and workflow runtime."""

    # ---------------------------------------------------------------
    # 1. External integrations
    # ---------------------------------------------------------------

    integrations = build_integrations(settings)

    # ---------------------------------------------------------------
    # 2. Shared PostgreSQL database engine
    # ---------------------------------------------------------------

    db_engine: AsyncEngine | None = None
    db_session_factory = None

    postgres_required = (
        settings.lead_store_backend == LeadStoreBackend.POSTGRES
        or settings.workflow_store_backend == WorkflowStoreBackend.POSTGRES
    )

    if postgres_required:
        db_engine = create_engine(settings)
        db_session_factory = create_session_factory(db_engine)

        logger.info("Shared PostgreSQL database engine initialized")

    # ---------------------------------------------------------------
    # 3. Lead storage backend
    # ---------------------------------------------------------------

    if settings.lead_store_backend == LeadStoreBackend.POSTGRES:
        assert db_session_factory is not None

        lead_store: LeadStore = PostgresLeadStore(db_session_factory)

        logger.info("PostgreSQL LeadStore backend selected")

    else:
        lead_store = InMemoryLeadStore()

        logger.info("In-memory LeadStore backend selected")

    # ---------------------------------------------------------------
    # 4. Email sender and knowledge components
    # ---------------------------------------------------------------

    email_sender = MockEmailSender()

    embedder = HashingEmbeddingProvider(settings.embedding_dimension)

    vector_store = InMemoryVectorStore()

    retriever = Retriever(
        embedder,
        vector_store,
    )

    ingestion = IngestionPipeline(
        embedder,
        vector_store,
        chunk_size=settings.knowledge_chunk_size,
        chunk_overlap=settings.knowledge_chunk_overlap,
    )

    # ---------------------------------------------------------------
    # 5. Property catalog
    # ---------------------------------------------------------------

    # Supplied-source workspaces must not recommend records from the demo seed.
    catalog = (
        InMemoryPropertyCatalog(()) if settings.agent_knowledge_path else InMemoryPropertyCatalog()
    )

    # ---------------------------------------------------------------
    # 6. Tool registration
    # ---------------------------------------------------------------

    tools = ToolRegistry()
    assigned_sources = (
        AssignedSources(settings.agent_knowledge_path) if settings.agent_knowledge_path else None
    )

    for tool in (
        CRMFindLeadsTool(integrations.crm),
        CRMCreateLeadTool(integrations.crm),
        CRMUpdateLeadTool(integrations.crm),
        CRMAddNoteTool(integrations.crm),
        WhatsAppSendTool(integrations.whatsapp),
        EmailRenderTemplateTool(),
        EmailSendTool(email_sender),
        CalendarCreateEventTool(integrations.calendar),
        PropertySearchTool(catalog),
        PropertyMatchTool(catalog),
        DocumentSearchTool(retriever, assigned_sources),
        LeadDuplicateSearchTool(lead_store),
        LeadSaveTool(lead_store),
        LeadScoringTool(),
        SalesAnalyticsTool(),
    ):
        tools.register(tool)

    # ---------------------------------------------------------------
    # 7. Audit, approvals and tracing
    # ---------------------------------------------------------------

    audit = InMemoryAuditSink()

    approvals = InMemoryApprovalStore()

    tracer = build_tracer()

    gateway = ToolGateway(
        tools,
        approval_policy=ApprovalPolicy.from_settings(settings),
        approvals=approvals,
        idempotency=InMemoryIdempotencyStore(),
        audit=audit,
        tracer=tracer,
    )

    # ---------------------------------------------------------------
    # 8. Agent dependencies
    # ---------------------------------------------------------------

    deps = AgentDependencies(
        supplied_knowledge_only=assigned_sources is not None,
        gateway=gateway,
        llm=build_model_router(settings),
        memory=InMemoryConversationMemory(),
        events=InMemoryEventBus(),
        tracer=tracer,
        executions=InMemoryExecutionRecorder(),
    )

    # ---------------------------------------------------------------
    # 9. Agent registry
    # ---------------------------------------------------------------

    agents = AgentRegistry(
        deps,
        default_timeout=settings.agent_default_timeout_seconds,
    )

    # ---------------------------------------------------------------
    # 10. Workflow execution history backend
    # ---------------------------------------------------------------

    if settings.workflow_store_backend == WorkflowStoreBackend.POSTGRES:
        assert db_session_factory is not None

        workflow_store: PostgresWorkflowRunStore | InMemoryWorkflowRunStore = (
            PostgresWorkflowRunStore(db_session_factory)
        )

        logger.info("PostgreSQL WorkflowRunStore backend selected")

    else:
        workflow_store = InMemoryWorkflowRunStore()

        logger.info("In-memory WorkflowRunStore backend selected")

    # ---------------------------------------------------------------
    # 11. Workflow runner
    # ---------------------------------------------------------------

    runner = WorkflowRunner(
        agents,
        workflow_store,
    )

    # ---------------------------------------------------------------
    # 12. Return complete platform runtime
    # ---------------------------------------------------------------

    return PlatformRuntime(
        settings=settings,
        integrations=integrations,
        tools=tools,
        gateway=gateway,
        deps=deps,
        agents=agents,
        runner=runner,
        lead_store=lead_store,
        ingestion=ingestion,
        retriever=retriever,
        audit=audit,
        approvals=approvals,
        email_sender=email_sender,
        assigned_sources=assigned_sources,
        _db_engine=db_engine,
    )
