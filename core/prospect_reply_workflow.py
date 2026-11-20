"""Pure reply-to-human-task rules. No inbox, webhook, sending, calling or storage."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Annotated, Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

Identity = Annotated[str, StringConstraints(pattern=r'^[a-zA-Z0-9-]{1,100}$')]
Key = Annotated[str, StringConstraints(pattern=r'^[a-f0-9]{32}$')]


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class ConfirmedProspectLink(Model):
    """Must be constructed from tenant-authorized records, never webhook claims."""
    tenant_id: Identity
    prospect_id: Identity
    owner_id: Identity
    confirmed: Literal[True]
    archived: bool = False

    @field_validator('confirmed', mode='before')
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True: raise ValueError('Explicit confirmed attribution required')
        return value


class ReplyEvent(Model):
    channel: Literal['email', 'whatsapp']
    provider_event_id: str = Field(min_length=1, max_length=200)
    kind: Literal['reply', 'opt_out', 'auto_reply', 'bounce']
    received_at: AwareDatetime
    text: str = Field(min_length=1, max_length=10_000)


class RecordedReply(Model):
    id: Key
    prospect_id: Identity
    fingerprint: Key
    event: ReplyEvent
    recorded_at: AwareDatetime


class HumanCallbackTask(Model):
    id: Key
    prospect_id: Identity
    owner_id: Identity
    event_ids: list[Key] = Field(min_length=1, max_length=2000)
    status: Literal['needs_review', 'completed', 'cancelled'] = 'needs_review'
    calling_permission: Literal['unknown'] = 'unknown'
    created_at: AwareDatetime
    updated_at: AwareDatetime
    completion_note: str = Field(default='', max_length=1500)


class OwnerNotification(Model):
    id: Key
    event_id: Key
    prospect_id: Identity
    owner_id: Identity
    kind: Literal['reply_received', 'opt_out_received', 'delivery_issue']
    delivery_state: Literal['not_connected'] = 'not_connected'
    callback_task_id: Key | None = None
    callback_blocked: Literal['suppressed', 'archived'] | None = None
    created_at: AwareDatetime


class ContactSuppression(Model):
    prospect_id: Identity
    event_id: Key
    created_at: AwareDatetime


class ReplyWorkflow(Model):
    version: Literal[1] = 1
    tenant_id: Identity
    replies: list[RecordedReply] = Field(default_factory=list, max_length=2000)
    tasks: list[HumanCallbackTask] = Field(default_factory=list, max_length=2000)
    notifications: list[OwnerNotification] = Field(default_factory=list, max_length=2000)
    suppressions: list[ContactSuppression] = Field(default_factory=list, max_length=500)

    @model_validator(mode='after')
    def coherent(self):
        for rows in (self.replies, self.tasks, self.notifications):
            if len({row.id for row in rows}) != len(rows): raise ValueError('Duplicate workflow record')
        events = {row.id: row for row in self.replies}
        tasks = {row.id: row for row in self.tasks}
        suppressed = {row.prospect_id for row in self.suppressions}
        if len(suppressed) != len(self.suppressions): raise ValueError('Duplicate suppression')
        pending = set()
        for row in self.replies:
            if event_key(self.tenant_id, row.event) != row.id or fingerprint(row.event) != row.fingerprint:
                raise ValueError('Reply fingerprint mismatch')
        for task in self.tasks:
            if len(set(task.event_ids)) != len(task.event_ids): raise ValueError('Duplicate task event')
            if any(key not in events or events[key].prospect_id != task.prospect_id or events[key].event.kind != 'reply' for key in task.event_ids):
                raise ValueError('Task reply attribution mismatch')
            if task.updated_at < task.created_at: raise ValueError('Invalid task clock')
            if task.status == 'needs_review':
                if task.prospect_id in pending or task.prospect_id in suppressed: raise ValueError('Duplicate or suppressed callback')
                pending.add(task.prospect_id)
        seen_alerts = set()
        for alert in self.notifications:
            if alert.event_id not in events or events[alert.event_id].prospect_id != alert.prospect_id:
                raise ValueError('Notification attribution mismatch')
            if alert.event_id in seen_alerts: raise ValueError('Duplicate reply notification')
            seen_alerts.add(alert.event_id)
            if alert.callback_task_id is not None:
                task = tasks.get(alert.callback_task_id)
                if task is None or alert.event_id not in task.event_ids or task.prospect_id != alert.prospect_id:
                    raise ValueError('Notification task mismatch')
        for suppression in self.suppressions:
            event = events.get(suppression.event_id)
            if event is None or event.prospect_id != suppression.prospect_id or event.event.kind != 'opt_out':
                raise ValueError('Suppression evidence mismatch')
        return self


def hashed(*parts):
    return sha256(json.dumps(parts, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()[:32]


def event_key(tenant_id, event):
    return hashed(tenant_id, event.channel, event.provider_event_id)


def fingerprint(event):
    return hashed(event.model_dump(mode='json'))


def validated(value):
    return ReplyWorkflow.model_validate(value.model_dump())


def record_reply(workflow: ReplyWorkflow, tenant_id: str, link: ConfirmedProspectLink, event: ReplyEvent, now=None):
    """Return an atomic new state. Caller must lock/persist it transactionally.

    The caller must authenticate the inbound event, classify it and match exactly
    one existing prospect in the same tenant. No address/name matching occurs here.
    All resulting notifications are unsent and tasks require human review.
    """
    value = validated(workflow).model_copy(deep=True)
    link = ConfirmedProspectLink.model_validate(link.model_dump())
    event = ReplyEvent.model_validate(event.model_dump())
    if tenant_id != value.tenant_id or tenant_id != link.tenant_id: raise ValueError('Tenant mismatch')
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None: raise ValueError('Timezone-aware timestamp required')
    key = event_key(tenant_id, event)
    for old in value.replies:
        if old.id == key:
            if old.fingerprint != fingerprint(event) or old.prospect_id != link.prospect_id:
                raise ValueError('Conflicting replay; manual investigation required')
            return value
    value.replies.append(RecordedReply(id=key, prospect_id=link.prospect_id, fingerprint=fingerprint(event), event=event, recorded_at=stamp))
    if event.kind == 'auto_reply': return validated(value)
    task = None
    blocked = None
    if event.kind == 'opt_out':
        if not any(row.prospect_id == link.prospect_id for row in value.suppressions):
            value.suppressions.append(ContactSuppression(prospect_id=link.prospect_id, event_id=key, created_at=stamp))
        for row in value.tasks:
            if row.prospect_id == link.prospect_id and row.status == 'needs_review':
                row.status = 'cancelled'; row.updated_at = max(stamp, row.updated_at)
                row.completion_note = 'Cancelled after a recorded opt-out. Do not call.'
    elif event.kind == 'reply':
        blocked = 'suppressed' if any(row.prospect_id == link.prospect_id for row in value.suppressions) else 'archived' if link.archived else None
        if blocked is None:
            task = next((row for row in value.tasks if row.prospect_id == link.prospect_id and row.status == 'needs_review'), None)
            if task is None:
                task = HumanCallbackTask(id=hashed(tenant_id, 'callback', key), prospect_id=link.prospect_id, owner_id=link.owner_id, event_ids=[key], created_at=stamp, updated_at=stamp)
                value.tasks.append(task)
            else:
                # Preserve an existing task's owner; later explicit reassignment is separate.
                task.event_ids.append(key); task.updated_at = max(stamp, task.updated_at)
    kind = {'reply': 'reply_received', 'opt_out': 'opt_out_received', 'bounce': 'delivery_issue'}[event.kind]
    value.notifications.append(OwnerNotification(id=hashed(tenant_id, 'notification', key), event_id=key, prospect_id=link.prospect_id,
        owner_id=task.owner_id if task else link.owner_id, kind=kind, callback_task_id=task.id if task else None,
        callback_blocked=blocked, created_at=stamp))
    return validated(value)


def close_task(workflow: ReplyWorkflow, tenant_id: str, owner_id: str, task_id: str, status: Literal['completed', 'cancelled'], note: str, now=None):
    """Record a human callback outcome, never place a call or grant permission."""
    value = validated(workflow).model_copy(deep=True)
    if tenant_id != value.tenant_id: raise ValueError('Tenant mismatch')
    if status not in {'completed', 'cancelled'} or not note.strip(): raise ValueError('Human outcome and note required')
    task = next((row for row in value.tasks if row.id == task_id), None)
    if task is None or task.owner_id != owner_id: raise ValueError('Assigned owner required')
    if task.status != 'needs_review': raise ValueError('Task is already closed')
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None or stamp < task.updated_at: raise ValueError('Invalid outcome timestamp')
    task.status = status; task.completion_note = note.strip(); task.updated_at = stamp
    return validated(value)
