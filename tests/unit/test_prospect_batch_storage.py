import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
from sqlalchemy import create_engine,insert,update
from core import prospect_research_batch as engine
from database import prospect_research_batches as db
from database.prospect_research import metadata,RevisionConflict,UnknownOrganization,workspaces,read_workspace


class StoreChecks(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://');metadata.tables['organizations'].create(self.engine);workspaces.create(self.engine)
        with self.engine.begin() as conn:
            conn.execute(insert(metadata.tables['organizations']),[{'id':uuid.uuid4(),'name':'Test A','slug':'a','is_active':True},{'id':uuid.uuid4(),'name':'Test B','slug':'b','is_active':True}]);db.initialize(conn,'a')
    def tearDown(self):self.engine.dispose()
    def test_create_read_and_summary(self):
        with self.engine.begin() as conn:
            saved=db.create_batch(conn,'a','Dubai','linkedin',500);self.assertEqual(saved['revision'],1);self.assertEqual(len(saved['state']['queries']),60);self.assertEqual(db.read_batch(conn,'a',saved['state']['id']),saved);summary=db.list_batches(conn,'a')[0];self.assertEqual(summary['count'],0);self.assertNotIn('candidates',summary)
    def test_tenant_isolation_and_unknown_org(self):
        with self.engine.begin() as conn:
            saved=db.create_batch(conn,'a','Dubai','linkedin',500)
            self.assertEqual(db.list_batches(conn,'b'),[])
            with self.assertRaises(db.BatchNotFound):db.read_batch(conn,'b',saved['state']['id'])
            with self.assertRaises(UnknownOrganization):db.list_batches(conn,'unknown')
    def test_stale_revision_does_not_overwrite(self):
        with self.engine.begin() as conn:
            saved=db.create_batch(conn,'a','Dubai','web',500);paused=db.change_batch(conn,'a',saved['state']['id'],1,'pause');self.assertEqual(paused['revision'],2)
            with self.assertRaises(RevisionConflict):db.change_batch(conn,'a',saved['state']['id'],1,'cancel')
            self.assertEqual(db.read_batch(conn,'a',saved['state']['id'])['state']['status'],'paused')
    def test_forged_state_identity_refused(self):
        with self.engine.begin() as conn:
            saved=db.create_batch(conn,'a','Dubai','web',500)
            with self.assertRaises(ValueError):db.write_batch(conn,'a',saved['state']['id'],1,{**saved['state'],'tenant_id':'b'})
    def test_schema_initialization_preserves_workspace_and_jobs(self):
        with self.engine.begin() as conn:
            before=read_workspace(conn,'a');saved=db.create_batch(conn,'a','Dubai','web',500);db.initialize(conn,'a');db.initialize(conn,'a');self.assertEqual(read_workspace(conn,'a'),before);self.assertEqual(db.read_batch(conn,'a',saved['state']['id']),saved)
    def test_twenty_job_capacity(self):
        with self.engine.begin() as conn:
            for _ in range(20):db.create_batch(conn,'a','Dubai','web',500)
            with self.assertRaises(db.BatchCapacity):db.create_batch(conn,'a','Dubai','web',500)
    def test_lock_identity_is_stable_and_tenant_specific(self):
        self.assertEqual(db.lock_id('a','one'),db.lock_id('a','one'));self.assertNotEqual(db.lock_id('a','one'),db.lock_id('b','one'));self.assertTrue(-(2**63)<=db.lock_id('a','one')<2**63)


class FakeConnection:
    def __init__(self,conn,available=True,fail_write=False):self.conn=conn;self.available=available;self.events=[];self.fail_write=fail_write;self.sync_calls=0
    async def scalar(self,statement,params):self.events.append('lock');assert 'pg_try_advisory_lock' in str(statement);return self.available
    async def commit(self):self.conn.commit();self.events.append('commit')
    async def rollback(self):self.conn.rollback();self.events.append('rollback')
    async def execute(self,statement,params):assert 'pg_advisory_unlock' in str(statement);self.events.append('unlock')
    async def invalidate(self):self.events.append('invalidate')
    async def run_sync(self,fn):
        self.sync_calls+=1
        if self.fail_write and self.sync_calls==2:raise RuntimeError('checkpoint unavailable')
        return fn(self.conn)


class LockChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://');metadata.tables['organizations'].create(self.engine)
        self.conn=self.engine.connect();self.conn.execute(insert(metadata.tables['organizations']).values(id=uuid.uuid4(),name='A',slug='a',is_active=True));db.initialize(self.conn,'a');self.saved=db.create_batch(self.conn,'a','Dubai','linkedin',500);self.conn.commit();self.id=self.saved['state']['id']
    def tearDown(self):self.conn.close();self.engine.dispose()
    async def test_provider_runs_only_after_uncertain_checkpoint_commit(self):
        connection=FakeConnection(self.conn)
        async def search(settings,query):
            self.assertEqual(connection.events[-1],'commit');saved=db.read_batch(self.conn,'a',self.id);self.assertEqual(saved['revision'],2);self.assertEqual(saved['state']['status'],'request_uncertain')
            return {'provider':'serpapi','engine':'google','query':query.query,'scope':query.scope,'contacts_saved':False,'outreach_enabled':False,'automatic_collection':False,'results':[{'title':'Public example','url':'https://www.linkedin.com/in/example','snippet':'Business profile'}]}
        with patch.object(engine,'configured',return_value=True),patch.object(engine,'reserve_search',AsyncMock()),patch.object(engine,'search_once',side_effect=search):
            result=await db.advance_locked(connection,None,'a',self.id,1)
        self.assertEqual(result['revision'],3);self.assertEqual(len(result['state']['candidates']),1);self.assertIn('unlock',connection.events)
    async def test_concurrent_lock_rejected_before_provider_or_read(self):
        connection=FakeConnection(self.conn,available=False)
        with patch.object(db,'advance_batch',AsyncMock()) as advance:
            with self.assertRaises(db.BatchBusy):await db.advance_locked(connection,None,'a',self.id,1)
        advance.assert_not_called();self.assertEqual(connection.sync_calls,0)
    async def test_stale_revision_cannot_spend_credit(self):
        connection=FakeConnection(self.conn)
        with patch.object(db,'advance_batch',AsyncMock()) as advance:
            with self.assertRaises(RevisionConflict):await db.advance_locked(connection,None,'a',self.id,2)
        advance.assert_not_called();self.assertIn('unlock',connection.events)
    async def test_storage_failure_blocks_provider_and_unlocks(self):
        connection=FakeConnection(self.conn,fail_write=True);provider=AsyncMock()
        with patch.object(engine,'configured',return_value=True),patch.object(engine,'reserve_search',AsyncMock()),patch.object(engine,'search_once',provider):
            with self.assertRaises(RuntimeError):await db.advance_locked(connection,None,'a',self.id,1)
        provider.assert_not_called();self.assertIn('unlock',connection.events);self.assertEqual(db.read_batch(self.conn,'a',self.id)['revision'],1)
    async def test_pause_uses_same_lock_without_search(self):
        connection=FakeConnection(self.conn)
        with patch.object(db,'advance_batch',AsyncMock()) as advance:result=await db.advance_locked(connection,None,'a',self.id,1,'pause')
        self.assertEqual(result['state']['status'],'paused');advance.assert_not_called();self.assertEqual(connection.events[0],'lock');self.assertIn('unlock',connection.events)


class RouteChecks(unittest.TestCase):
    def setUp(self):
        from core.config.settings import Settings
        from workflows.runtime import build_runtime
        from apps.api.app.main import create_app
        from fastapi.testclient import TestClient
        from apps.api.app.api.v1.routes import prospect_batches
        self.module=prospect_batches
        settings=Settings(_env_file=None,environment='test',auth_mode='dev',enable_dev_routes=True,prospect_storage_enabled=True,lead_store_backend='memory',workflow_store_backend='memory',integrations_mode='mock',llm_provider='mock',rate_limit_per_minute=1000)
        self.runtime=build_runtime(settings);self.app=create_app(settings,self.runtime);self.client=TestClient(self.app);self.client.__enter__();self.path='/api/v1/prospect-research/batches'
    def tearDown(self):self.client.__exit__(None,None,None)
    def test_list_has_no_side_effect_and_tenant_from_principal(self):
        fake=AsyncMock(return_value=[])
        with patch.object(self.module,'access_batches',fake):r=self.client.get(self.path)
        self.assertEqual(r.status_code,200);self.assertFalse(r.json()['scheduled']);self.assertEqual(r.headers['cache-control'],'no-store');self.assertEqual(fake.call_args.args[1:3],('demo-org','list'))
    def test_create_does_not_advance(self):
        fake=AsyncMock(return_value={'revision':1,'state':{}})
        with patch.object(self.module,'access_batches',fake):r=self.client.post(self.path,json={'location':'Dubai','target':500,'scope':'linkedin'})
        self.assertEqual(r.status_code,200);self.assertEqual(fake.call_args.args[2],'create')
    def test_viewer_cannot_create_or_advance(self):
        with patch.object(self.module,'access_batches',AsyncMock()) as fake:
            self.assertEqual(self.client.post(self.path,headers={'X-Dev-Roles':'viewer'},json={}).status_code,403);self.assertEqual(self.client.post(self.path+'/job/actions',headers={'X-Dev-Roles':'viewer'},json={'revision':1,'action':'advance'}).status_code,403)
        fake.assert_not_called()
    def test_origin_tenant_injection_and_unknown_action_refused(self):
        with patch.object(self.module,'access_batches',AsyncMock()) as fake:
            self.assertEqual(self.client.post(self.path,headers={'Origin':'https://example.com'},json={}).status_code,403);self.assertEqual(self.client.post(self.path,json={'tenant_id':'other'}).status_code,422);self.assertEqual(self.client.post(self.path+'/job/actions',json={'revision':1,'action':'send_messages'}).status_code,422)
        fake.assert_not_called()
    def test_busy_and_stale_do_not_retry(self):
        for error in (db.BatchBusy(),RevisionConflict()):
            fake=AsyncMock(side_effect=error)
            with patch.object(self.module,'access_batches',fake):r=self.client.post(self.path+'/job/actions',json={'revision':1,'action':'advance'})
            self.assertEqual(r.status_code,409);self.assertEqual(fake.call_count,1)
    def test_failures_do_not_disclose_credentials(self):
        with patch.object(self.module,'access_batches',AsyncMock(side_effect=RuntimeError('PRIVATE_CONNECTION_SECRET'))):r=self.client.get(self.path)
        self.assertEqual(r.status_code,503);self.assertNotIn('PRIVATE_CONNECTION_SECRET',r.text)
    def test_action_uses_server_tenant_and_revision(self):
        fake=AsyncMock(return_value={'revision':2,'state':{}})
        with patch.object(self.module,'access_batches',fake):r=self.client.post(self.path+'/job/actions',json={'revision':1,'action':'pause'})
        self.assertEqual(r.status_code,200);self.assertEqual(fake.call_args.args[1:3],('demo-org','pause'));self.assertEqual(fake.call_args.kwargs['revision'],1)


if __name__=='__main__':unittest.main()
