"""Offline contracts for the unregistered source-discovery batch engine."""
import asyncio
import json
import unittest
from datetime import datetime,timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
from pydantic import ValidationError
from core import prospect_research_batch as engine

NOW=datetime(2026,10,27,12,tzinfo=timezone.utc)


def batch(target=500):return engine.new_batch('test-batch','org-a',target=target)


def response(value,urls=None):
    q=value.queries[value.cursor]
    return {'provider':'serpapi','engine':'google','query':q.query,'scope':q.scope,'contacts_saved':False,'outreach_enabled':False,'automatic_collection':False,'results':[{'title':'Public Example Business','url':url,'snippet':'Director at a company; buying intent unknown.'} for url in (urls or ['https://www.linkedin.com/in/example-director'])]}


class ModelChecks(unittest.TestCase):
    def test_roles_target_and_public_scope(self):
        value=batch();self.assertEqual(value.target,500);self.assertEqual(len(value.queries),6);self.assertTrue(all(q.scope=='linkedin' for q in value.queries))
    def test_no_contacts_permission_or_wealth_fields(self):
        self.assertNotIn('email',batch().model_dump());self.assertNotIn('wealth',batch().model_dump());self.assertNotIn('outreach_enabled',batch().model_dump())
    def test_target_and_query_caps(self):
        for target in (0,501):
            with self.assertRaises(ValidationError):batch(target)
        with self.assertRaises(ValidationError):engine.ResearchBatch(id='x',tenant_id='a',queries=[batch().queries[0]]*101)
    def test_duplicate_queries_refused(self):
        with self.assertRaises(ValidationError):engine.ResearchBatch(id='x',tenant_id='a',queries=[batch().queries[0]]*2)
    def test_private_scope_refused(self):
        with self.assertRaises(ValidationError):engine.new_batch('x','a',scope='private')
    def test_completed_cannot_claim_missing_target(self):
        with self.assertRaises(ValidationError):engine.ResearchBatch.model_validate({**batch().model_dump(),'status':'completed'})
    def test_pause_resume_and_cancel_keep_sources(self):
        paused=engine.transition(batch(),'org-a','pause');self.assertEqual(paused.status,'paused');self.assertEqual(engine.transition(paused,'org-a','resume').status,'ready');self.assertEqual(engine.transition(paused,'org-a','cancel').status,'cancelled')
    def test_tenant_transition_refused(self):
        with self.assertRaises(ValueError):engine.transition(batch(),'org-b','pause')
    def test_fragments_do_not_create_duplicate_sources(self):
        self.assertEqual(engine.source_id('https://www.linkedin.com/in/x#first'),engine.source_id('https://www.linkedin.com/in/x#second'))


class AsyncChecks(unittest.IsolatedAsyncioTestCase):
    async def run_engine(self,value=None,result=None,reserve_error=None,search_error=None,checkpoint=None):
        value=value or batch();saved=[]
        async def save(data):saved.append(data)
        reserve=AsyncMock(side_effect=reserve_error);search=AsyncMock(return_value=result or response(value),side_effect=search_error)
        with patch.object(engine,'configured',return_value=True),patch.object(engine,'reserve_search',reserve),patch.object(engine,'search_once',search):
            out=await engine.advance_batch(value,SimpleNamespace(),'org-a',checkpoint or save,NOW)
        return out,saved,reserve,search

    async def test_one_request_and_checkpoint_before_provider(self):
        saved=[]
        async def save(data):saved.append(data)
        async def search(*args):
            self.assertEqual(saved[-1]['status'],'request_uncertain');self.assertEqual(saved[-1]['cursor'],1);return response(batch())
        with patch.object(engine,'configured',return_value=True),patch.object(engine,'reserve_search',AsyncMock()),patch.object(engine,'search_once',side_effect=search) as provider:
            out=await engine.advance_batch(batch(),None,'org-a',save,NOW)
        self.assertEqual(provider.call_count,1);self.assertEqual(out.provider_attempts,1);self.assertEqual(out.cursor,1);self.assertEqual(len(out.candidates),1);self.assertEqual(saved[-1]['status'],'ready')

    async def test_input_snapshot_is_not_mutated(self):
        original=batch();await self.run_engine(original);self.assertEqual(original.cursor,0);self.assertEqual(original.candidates,[])

    async def test_checkpoint_failure_blocks_provider(self):
        provider=AsyncMock()
        with patch.object(engine,'configured',return_value=True),patch.object(engine,'reserve_search',AsyncMock()),patch.object(engine,'search_once',provider):
            with self.assertRaises(RuntimeError):await engine.advance_batch(batch(),None,'org-a',AsyncMock(side_effect=RuntimeError('storage unavailable')),NOW)
        provider.assert_not_called()

    async def test_quota_wait_until_dubai_midnight(self):
        out,saved,_,provider=await self.run_engine(reserve_error=engine.DiscoveryLimit());self.assertEqual(out.status,'quota_wait');self.assertEqual(out.resume_at.isoformat(),'2026-10-28T00:00:00+04:00');self.assertEqual(out.cursor,0);self.assertEqual(out.provider_attempts,0);provider.assert_not_called()
        out,_,reserve,provider=await self.run_engine(value=out);reserve.assert_not_called();provider.assert_not_called()

    async def test_quota_service_failure_has_no_provider_call(self):
        out,_,_,provider=await self.run_engine(reserve_error=engine.DiscoveryUnavailable());self.assertEqual(out.status,'error');provider.assert_not_called()

    async def test_paused_cancelled_and_uncertain_never_run(self):
        for status in ('paused','cancelled','request_uncertain','error','queries_exhausted'):
            value=batch().model_copy(update={'status':status});_,_,reserve,provider=await self.run_engine(value=value);reserve.assert_not_called();provider.assert_not_called()

    async def test_provider_failure_not_retried_or_disclosed(self):
        out,saved,_,provider=await self.run_engine(search_error=RuntimeError('PRIVATE_SECRET'));self.assertEqual(out.status,'request_uncertain');self.assertEqual(provider.call_count,1);self.assertNotIn('PRIVATE_SECRET',json.dumps(saved));self.assertEqual(out.cursor,1)

    async def test_uncertain_query_requires_explicit_skip(self):
        out,_,_,_=await self.run_engine(search_error=engine.DiscoveryUnavailable());next_state=engine.transition(out,'org-a','skip_uncertain');self.assertEqual(next_state.cursor,1);self.assertEqual(next_state.status,'ready')

    async def test_target_stops_and_deduplicates(self):
        value=batch(target=1);result=response(value,['https://www.linkedin.com/in/x#one','https://www.linkedin.com/in/x#two','https://www.linkedin.com/in/y']);out,_,_,_=await self.run_engine(value,result);self.assertEqual(out.status,'completed');self.assertEqual(len(out.candidates),1)
        _,_,reserve,provider=await self.run_engine(value=out);reserve.assert_not_called();provider.assert_not_called()

    async def test_last_query_marks_partial_not_complete(self):
        value=batch().model_copy(update={'cursor':5});out,_,_,_=await self.run_engine(value);self.assertEqual(out.status,'queries_exhausted');self.assertEqual(len(out.candidates),1)

    async def test_wrong_scope_or_claimed_contacts_response_rejected(self):
        for update in ({'results':[{'title':'Wrong domain','snippet':'text','url':'https://example.com/'}]},{'contacts_saved':True},{'results':[{'title':'Bad','snippet':'text','url':'javascript:alert(1)'}]}):
            out,_,_,_=await self.run_engine(result={**response(batch()),**update});self.assertEqual(out.status,'request_uncertain');self.assertEqual(out.candidates,[])

    async def test_cross_tenant_does_not_reserve_or_search(self):
        provider=AsyncMock();reserve=AsyncMock()
        with patch.object(engine,'reserve_search',reserve),patch.object(engine,'search_once',provider):
            with self.assertRaises(ValueError):await engine.advance_batch(batch(),None,'org-b',AsyncMock(),NOW)
        reserve.assert_not_called();provider.assert_not_called()

    async def test_disabled_provider_does_not_checkpoint_or_request(self):
        checkpoint=AsyncMock();provider=AsyncMock()
        with patch.object(engine,'configured',return_value=False),patch.object(engine,'search_once',provider):
            with self.assertRaises(ValueError):await engine.advance_batch(batch(),None,'org-a',checkpoint,NOW)
        checkpoint.assert_not_called();provider.assert_not_called()

    async def test_resumes_after_quota_time_without_skipping_query(self):
        value=batch().model_copy(update={'status':'quota_wait','resume_at':datetime(2026,10,27,0,tzinfo=timezone.utc)})
        out,_,reserve,provider=await self.run_engine(value=value);reserve.assert_called_once();provider.assert_called_once();self.assertEqual(out.cursor,1)

    async def test_duplicate_source_across_different_queries(self):
        first,_,_,_=await self.run_engine();second,_,_,_=await self.run_engine(value=first);self.assertEqual(len(second.candidates),1);self.assertEqual(second.provider_attempts,2)

    async def test_500_candidate_target_with_simulated_budgeted_requests(self):
        value=engine.ResearchBatch(id='bulk-test',tenant_id='org-a',queries=[engine.BatchQuery(role='ceo',scope='linkedin',query=f'Dubai CEO public business profile sector {i}') for i in range(60)])
        requests=[];checkpoints=[]
        async def provider(settings,query):
            index=len(requests);requests.append(query)
            return {'provider':'serpapi','engine':'google','query':query.query,'scope':query.scope,'contacts_saved':False,'outreach_enabled':False,'automatic_collection':False,'results':[{'title':f'Public source {index*10+j}','url':f'https://www.linkedin.com/in/example-{index*10+j}','snippet':'Fictional source; no buying ability inferred.'} for j in range(10)]}
        async def save(data):checkpoints.append(data)
        with patch.object(engine,'configured',return_value=True),patch.object(engine,'reserve_search',AsyncMock()) as reserve,patch.object(engine,'search_once',side_effect=provider):
            for _ in range(60):
                value=await engine.advance_batch(value,None,'org-a',save,NOW)
                if value.status=='completed':break
            value=await engine.advance_batch(value,None,'org-a',save,NOW)
        self.assertEqual(value.status,'completed');self.assertEqual(len(value.candidates),500);self.assertEqual(len(requests),50);self.assertEqual(reserve.call_count,50);self.assertEqual(len(checkpoints),100)


if __name__=='__main__':unittest.main()
