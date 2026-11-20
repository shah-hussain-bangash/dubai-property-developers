"""Persistence-level status enums (stored as VARCHAR)."""

from __future__ import annotations

from enum import StrEnum


class OpportunityStage(StrEnum):
    DISCOVERY = "discovery"
    VIEWING = "viewing"
    NEGOTIATION = "negotiation"
    RESERVATION = "reservation"
    WON = "won"
    LOST = "lost"


class TaskType(StrEnum):
    FOLLOW_UP = "follow_up"
    CALL = "call"
    MEETING = "meeting"
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    INTERNAL = "internal"


class TaskStatus(StrEnum):
    OPEN = "open"
    DONE = "done"
    CANCELLED = "cancelled"
    OVERDUE = "overdue"


class ConversationStatus(StrEnum):
    OPEN = "open"
    WAITING_CUSTOMER = "waiting_customer"
    ESCALATED = "escalated"
    CLOSED = "closed"


class SenderType(StrEnum):
    CUSTOMER = "customer"
    AI_AGENT = "ai_agent"
    STAFF = "staff"
    SYSTEM = "system"


class DeliveryStatus(StrEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class ExecutionStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    PENDING_APPROVAL = "pending_approval"
    ESCALATED = "escalated"


class ConnectionStatus(StrEnum):
    NOT_CONFIGURED = "not_configured"
    ACTIVE = "active"
    ERROR = "error"
    DISABLED = "disabled"


class SyncDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class SyncStatus(StrEnum):
    SYNCED = "synced"
    PENDING = "pending"
    CONFLICT = "conflict"
    FAILED = "failed"


class DocumentStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class AccessLevel(StrEnum):
    PUBLIC = "public"  # may be quoted to customers
    INTERNAL = "internal"  # staff and agents only
    RESTRICTED = "restricted"  # explicit roles only
