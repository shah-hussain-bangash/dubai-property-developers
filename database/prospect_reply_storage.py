"""Tenant-scoped atomic reply/task snapshots. Provision explicitly; no API routes."""
import asyncio
from datetime import datetime, timezone
import json
from sqlalchemy import Table, Column, Uuid, Integer, JSON, DateTime, ForeignKey, CheckConstraint, select, insert, update, inspect
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from core.prospect_reply_workflow import ReplyWorkflow, ReplyEvent, ConfirmedProspectLink, record_reply, close_task
from database.prospect_research import metadata, organization, read_workspace, RevisionConflict

reply_workspaces = Table('prospect_reply_workspaces_v1', metadata,
    Column('organization_id', Uuid, ForeignKey('organizations.id', ondelete='RESTRICT'), primary_key=True),
    Column('revision', Integer, nullable=False),
    Column('state', JSON().with_variant(JSONB(), 'postgresql'), nullable=False),
    Column('updated_at', DateTime(timezone=True), nullable=False),
    CheckConstraint('revision > 0', name='ck_prospect_reply_revision'))


class UnknownProspect(Exception): pass


def decode(state, slug):
    # Strict models accept ISO datetimes in JSON mode, not untrusted Python strings.
    workflow = ReplyWorkflow.model_validate_json(json.dumps(state))
    if workflow.tenant_id != slug: raise ValueError('Stored reply tenant mismatch')
    return workflow


def read_replies(conn, slug):
    org = organization(conn, slug)
    row = conn.execute(select(reply_workspaces.c.revision, reply_workspaces.c.state).where(reply_workspaces.c.organization_id == org)).mappings().first()
    if row is None: return {'revision': 0, 'state': ReplyWorkflow(tenant_id=slug).model_dump(mode='json')}
    if type(row['revision']) is not int or row['revision'] < 1: raise ValueError('Stored reply revision invalid')
    return {'revision': row['revision'], 'state': decode(row['state'], slug).model_dump(mode='json')}


def _revision(expected, actual):
    if type(expected) is not int or expected < 0 or expected != actual: raise RevisionConflict()


def _save(conn, slug, org, revision, state, now):
    state = decode(state.model_dump(mode='json'), slug)
    values = {'revision': revision + 1, 'state': state.model_dump(mode='json'), 'updated_at': now}
    if revision == 0:
        conn.execute(insert(reply_workspaces).values(organization_id=org, **values))
    else:
        changed = conn.execute(update(reply_workspaces).where(reply_workspaces.c.organization_id == org, reply_workspaces.c.revision == revision).values(**values))
        if changed.rowcount != 1: raise RevisionConflict()
    return {'revision': revision + 1, 'state': values['state']}


def record_incoming(conn, slug, revision, prospect_id, owner_id, event: ReplyEvent, now=None):
    """Caller authenticates sender/owner and matches the reply before invoking.

    Organization row lock serializes writes, including first insertion. No commit
    occurs here: the enclosing transaction commits reply, task, alert and opt-out
    together. Exact event replays are read-only even with an older client revision.
    """
    org = organization(conn, slug, lock=True)
    stored = read_replies(conn, slug)
    state = decode(stored['state'], slug)
    prospect = next((p for p in read_workspace(conn, slug)['workspace']['prospects'] if p['id'] == prospect_id), None)
    if prospect is None: raise UnknownProspect()
    link = ConfirmedProspectLink(tenant_id=slug, prospect_id=prospect_id, owner_id=owner_id, confirmed=True, archived=prospect['status'] == 'archived')
    stamp = now or datetime.now(timezone.utc)
    changed = record_reply(state, slug, link, event, stamp)
    if changed == state: return stored
    _revision(revision, stored['revision'])
    return _save(conn, slug, org, stored['revision'], changed, stamp)


def close_callback(conn, slug, revision, owner_id, task_id, status, note, now=None):
    org = organization(conn, slug, lock=True)
    stored = read_replies(conn, slug)
    _revision(revision, stored['revision'])
    stamp = now or datetime.now(timezone.utc)
    changed = close_task(decode(stored['state'], slug), slug, owner_id, task_id, status, note, stamp)
    return _save(conn, slug, org, stored['revision'], changed, stamp)


def check_schema(conn):
    inspector = inspect(conn)
    columns = {row['name']: row for row in inspector.get_columns(reply_workspaces.name)}
    if set(columns) != {'organization_id', 'revision', 'state', 'updated_at'}: raise ValueError('Unexpected reply table columns')
    if set(inspector.get_pk_constraint(reply_workspaces.name)['constrained_columns']) != {'organization_id'}: raise ValueError('Unexpected reply primary key')
    if any(columns[name]['nullable'] for name in columns): raise ValueError('Nullable reply columns refused')
    if not isinstance(columns['revision']['type'], Integer) or not isinstance(columns['state']['type'], JSON) or not isinstance(columns['updated_at']['type'], DateTime):
        raise ValueError('Unexpected reply column types')
    foreign_keys = inspector.get_foreign_keys(reply_workspaces.name)
    if not any(row['constrained_columns'] == ['organization_id'] and row['referred_table'] == 'organizations' and row['referred_columns'] == ['id'] and row['options'].get('ondelete', '').upper() == 'RESTRICT' for row in foreign_keys):
        raise ValueError('Expected tenant foreign key missing')
    constraints = inspector.get_check_constraints(reply_workspaces.name)
    if not any(row['name'] == 'ck_prospect_reply_revision' and ''.join(row['sqltext'].replace('(', '').replace(')', '').split()) == 'revision>0' for row in constraints):
        raise ValueError('Expected reply revision constraint missing')


def initialize(conn, slug, check_only=False):
    organization(conn, slug)
    if not check_only: reply_workspaces.create(conn, checkfirst=True)
    check_schema(conn)
    return read_replies(conn, slug)


def make_engine(settings):
    return create_async_engine(settings.database_url.get_secret_value(), poolclass=NullPool, echo=False,
        hide_parameters=True, connect_args={'timeout': 8, 'command_timeout': 12})


async def access_reply_storage(settings, slug, operation='read', **kwargs):
    """No schema creation, whole-state replacement, delivery or retry endpoint."""
    if not settings.is_dev_like or not settings.enable_dev_routes or not settings.prospect_storage_enabled:
        raise ValueError('Isolated local research storage required')
    functions = {'read': read_replies, 'record': record_incoming, 'close': close_callback}
    if operation not in functions: raise ValueError('Unsupported reply operation')
    engine = make_engine(settings)
    try:
        async with engine.begin() as conn:
            return await conn.run_sync(lambda c: functions[operation](c, slug, **kwargs))
    finally: await engine.dispose()


async def provision(check_only=False):
    from core.config.settings import Settings
    settings = Settings()
    if not settings.is_dev_like or not settings.enable_dev_routes or not settings.prospect_storage_enabled:
        raise ValueError('Isolated local research storage required')
    engine = make_engine(settings)
    try:
        async with engine.begin() as conn:
            saved = await conn.run_sync(lambda c: initialize(c, settings.default_tenant_id, check_only))
        # Counts only; never print messages, names, addresses or database credentials.
        return {'table_ready': True, 'revision': saved['revision'], 'reply_count': len(saved['state']['replies']),
                'task_count': len(saved['state']['tasks']), 'outreach_enabled': False, 'inbox_connected': False}
    finally: await engine.dispose()
