"""Versioned local extension table, explicitly provisioned; no change to demo stores.

One workspace per active organization. An organization row lock serializes writers;
optimistic revisions reject outdated clients. API requests never create schema.
"""
import asyncio
import uuid
from sqlalchemy import MetaData, Table, Column, Uuid, Integer, JSON, CheckConstraint, ForeignKey, select, insert, update, inspect
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from database.models.identity import Organization
from schemas.prospect_research import ResearchWorkspace, WorkspaceWrite

metadata=MetaData()
Organization.__table__.to_metadata(metadata)
workspaces=Table('prospect_research_workspaces_v1',metadata,
    Column('organization_id',Uuid,ForeignKey('organizations.id',ondelete='RESTRICT'),primary_key=True),
    Column('revision',Integer,nullable=False),
    Column('workspace',JSON().with_variant(JSONB(),'postgresql'),nullable=False),
    CheckConstraint('revision > 0',name='ck_prospect_workspace_revision'))

class RevisionConflict(Exception): pass
class UnknownOrganization(Exception): pass

def organization(conn, slug, lock=False):
    query=select(Organization.id).where(Organization.slug==slug,Organization.is_active.is_(True))
    if lock: query=query.with_for_update()
    result=conn.scalar(query)
    if result is None: raise UnknownOrganization()
    return result

def read_workspace(conn, slug):
    org=organization(conn,slug)
    row=conn.execute(select(workspaces.c.revision,workspaces.c.workspace).where(workspaces.c.organization_id==org)).mappings().first()
    if not row: return {'revision':0,'workspace':ResearchWorkspace().model_dump()}
    return {'revision':row['revision'],'workspace':ResearchWorkspace.model_validate(row['workspace']).model_dump()}

def write_workspace(conn, slug, body:WorkspaceWrite):
    org=organization(conn,slug,lock=True)
    stored=conn.execute(select(workspaces.c.revision,workspaces.c.workspace).where(workspaces.c.organization_id==org)).mappings().first()
    current=stored['revision'] if stored else 0
    if body.revision!=current: raise RevisionConflict()
    incoming=body.workspace.model_dump()
    # Older dashboards omit the newly introduced contact fields. Preserve their
    # existing values during status/audience edits instead of silently erasing them.
    previous={p['id']:p for p in stored['workspace']['prospects']} if stored else {}
    for model,record in zip(body.workspace.prospects,incoming['prospects']):
        for field in ('whatsapp','whatsappSource','contactResources'):
            if field not in model.model_fields_set and field in previous.get(model.id,{}):
                record[field]=previous[model.id][field]
    validated=ResearchWorkspace.model_validate(incoming)
    values={'revision':current+1,'workspace':validated.model_dump()}
    if current:
        changed=conn.execute(update(workspaces).where(workspaces.c.organization_id==org,workspaces.c.revision==current).values(**values))
        if changed.rowcount!=1: raise RevisionConflict()
    else: conn.execute(insert(workspaces).values(organization_id=org,**values))
    return {'revision':current+1,'workspace':values['workspace']}

async def access_database(settings, slug, body=None):
    # URL stays in SecretStr until passed to the driver. Never log it.
    engine=create_async_engine(settings.database_url.get_secret_value(),poolclass=NullPool,echo=False,hide_parameters=True,connect_args={'timeout':8,'command_timeout':12})
    try:
        async with engine.begin() as conn:
            return await conn.run_sync(lambda c: read_workspace(c,slug) if body is None else write_workspace(c,slug,body))
    finally: await engine.dispose()

def initialize(conn, slug):
    # Provisioning may initialize only the known local demo tenant, without users,
    # roles, passwords or sessions. Custom or inactive tenants require attention.
    existing=conn.execute(select(Organization.id,Organization.is_active).where(Organization.slug==slug)).first()
    if existing is None and slug=='demo-org':
        conn.execute(insert(Organization.__table__).values(id=uuid.uuid4(),name='Local Prospect Research',slug=slug,is_active=True))
    organization(conn,slug)
    workspaces.create(conn,checkfirst=True)
    columns={c['name'] for c in inspect(conn).get_columns(workspaces.name)}
    if columns!={'organization_id','revision','workspace'}: raise ValueError('Unexpected prospect table schema')
    # Exercise decoding of this tenant's existing data, if any, without changing it.
    read_workspace(conn,slug)

async def provision():
    from core.config.settings import Settings
    settings=Settings()
    if not settings.is_dev_like or not settings.enable_dev_routes: raise ValueError('Local development setup only')
    engine=create_async_engine(settings.database_url.get_secret_value(),poolclass=NullPool,hide_parameters=True,connect_args={'timeout':8,'command_timeout':12})
    try:
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: initialize(c,settings.default_tenant_id))
        print('PASS: PostgreSQL prospect workspace table ready; organization and existing records preserved.')
    finally: await engine.dispose()

if __name__=='__main__':
    try: asyncio.run(provision())
    except Exception: raise SystemExit('Database setup could not complete. Existing tenant, database connectivity and schema need checking. No credentials are printed.') from None
