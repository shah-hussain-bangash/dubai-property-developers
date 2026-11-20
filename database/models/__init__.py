
"""Importing this package registers every model on Base.metadata."""

from database.models.agent import (
    AgentExecution,
    AIAgent,
    WorkflowExecution,
)
from database.models.background_job import BackgroundJob
from database.models.conversation import Conversation, Message
from database.models.crm import Contact, Lead, Opportunity, Task
from database.models.governance import ApprovalRequestRecord, AuditLog
from database.models.identity import Organization, Role, User, UserRole
from database.models.integration import (
    ExternalSyncRecord,
    IntegrationConnection,
)
from database.models.job_outbox import JobOutbox
from database.models.job_recovery_operation import JobRecoveryOperation
from database.models.knowledge import (
    ChunkEmbedding,
    KnowledgeChunk,
    KnowledgeDocument,
)
from database.models.tool_execution import ToolExecutionLedger
from database.models.property import (
    PaymentPlan,
    Project,
    Property,
    PropertyUnit,
)

__all__ = [
    "AIAgent",
    "AgentExecution",
    "ApprovalRequestRecord",
    "AuditLog",
    "BackgroundJob",
    "ChunkEmbedding",
    "Contact",
    "Conversation",
    "ExternalSyncRecord",
    "IntegrationConnection",
    "JobOutbox",
    "JobRecoveryOperation",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "Lead",
    "Message",
    "Opportunity",
    "Organization",
    "PaymentPlan",
    "Project",
    "Property",
    "PropertyUnit",
    "Role",
    "Task",
    "User",
    "UserRole",
    "ToolExecutionLedger",
    "WorkflowExecution",
]
