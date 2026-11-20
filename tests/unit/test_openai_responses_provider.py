"""Standalone adapter contract checks. All HTTP is handled in memory."""
import asyncio
import copy
import csv
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
if __name__ == '__main__' and len(sys.argv) > 1:
    del sys.argv[1]
sys.path.insert(0, str(ROOT))
held = {str((ROOT / row['source_path']).resolve()).casefold() for row in csv.DictReader(
    (ROOT / 'database/project_knowledge/reports/step458_manual_review_queue.csv').read_text(encoding='utf-8-sig').splitlines())}
attempts = {'connections': 0, 'held_execution': 0}


def audit(event, args):
    if event in ('socket.connect', 'socket.getaddrinfo'):
        # Windows asyncio creates a private socketpair for its event-loop wakeup.
        frame = sys._getframe(1)
        if (event == 'socket.connect' and frame.f_code.co_name == '_fallback_socketpair'
                and Path(frame.f_code.co_filename).name == 'socket.py'
                and args[1][0] in ('127.0.0.1', '::1')):
            return
        attempts['connections'] += 1
        raise RuntimeError('External connection blocked by adapter tests.')
    if event == 'exec' and str(Path(args[0].co_filename).resolve()).casefold() in held:
        attempts['held_execution'] += 1
        raise RuntimeError('Held source execution blocked by adapter tests.')


sys.addaudithook(audit)
import httpx
from pydantic import SecretStr
from core.exceptions.errors import ConfigurationError, DomainValidationError, IntegrationError, IntegrationNotConfiguredError, RateLimitExceededError
from core.llm.base import LLMProvider
from core.llm.openai_responses import OpenAIResponsesProvider
from core.llm.types import ChatMessage, LLMRequest


def request(**kwargs):
    return LLMRequest(messages=[ChatMessage(role='user', content='Fictional draft request')], **kwargs)


def success():
    return {'status': 'completed', 'error': None, 'model': 'unit-model-snapshot',
            'output': [{'type': 'message', 'role': 'assistant', 'status': 'completed',
                        'content': [{'type': 'output_text', 'text': 'Fictional response'}]}],
            'usage': {'input_tokens': 12, 'output_tokens': 3}}


def provider(handler, **kwargs):
    return OpenAIResponsesProvider(SecretStr('unit-sensitive-key'), transport=httpx.MockTransport(handler), **kwargs)


class Tests(unittest.IsolatedAsyncioTestCase):
    async def test_success_payload_and_usage(self):
        captured = []
        def handle(req):
            captured.append(req)
            return httpx.Response(200, json=success())
        result = await provider(handle).complete(request(metadata={'private': 'do-not-send'}), model='unit-model')
        self.assertEqual(result.text, 'Fictional response')
        self.assertEqual((result.input_tokens, result.output_tokens), (12, 3))
        self.assertEqual((result.provider, result.model, result.is_mock), ('openai', 'unit-model-snapshot', False))
        req = captured[0]
        self.assertEqual((req.method, str(req.url)), ('POST', 'https://api.openai.com/v1/responses'))
        self.assertEqual(req.headers['authorization'], 'Bearer unit-sensitive-key')
        self.assertEqual(req.extensions['timeout']['read'], 30)
        self.assertEqual(json.loads(req.content), {'model': 'unit-model', 'input': [{'role': 'user', 'content': 'Fictional draft request'}], 'max_output_tokens': 800, 'store': False, 'stream': False, 'tools': []})
        self.assertEqual(len(captured), 1)

    async def test_role_order_and_unicode(self):
        captured = []
        def handle(req):
            captured.append(json.loads(req.content)['input'])
            return httpx.Response(200, json=success())
        messages = [ChatMessage(role=role, content=text) for role, text in [('system', 'Rules'), ('user', 'مرحبا'), ('assistant', 'Earlier draft'), ('user', 'Continue')]]
        await provider(handle).complete(LLMRequest(messages=messages), model='unit-model')
        self.assertEqual(captured[0], [{'role': m.role.value, 'content': m.content} for m in messages])

    async def test_temperature_is_explicit_model_capability(self):
        captured = []
        def handle(req):
            captured.append(json.loads(req.content))
            return httpx.Response(200, json=success())
        await provider(handle).complete(request(), model='unit-model')
        await provider(handle, supports_temperature=True).complete(request(temperature=0.7), model='unit-model')
        self.assertNotIn('temperature', captured[0])
        self.assertEqual(captured[1]['temperature'], 0.7)

    async def test_invalid_configuration_rejected(self):
        for key in [None, 'raw-key', SecretStr(''), SecretStr(' key'), SecretStr('key\nheader')]:
            with self.subTest(key_type=type(key).__name__), self.assertRaises(ConfigurationError):
                OpenAIResponsesProvider(key)
        for value in [0, -1, 121, True, float('nan'), float('inf')]:
            with self.subTest(timeout=repr(value)), self.assertRaises(ConfigurationError):
                OpenAIResponsesProvider(SecretStr('unit-key'), timeout_seconds=value)

    async def test_invalid_input_rejected_before_http(self):
        calls = []
        p = provider(lambda req: calls.append(req))
        cases = [(request(), ''), (request(), 'bad\nmodel'), (LLMRequest(messages=[]), 'unit-model'),
                 (LLMRequest(messages=[ChatMessage(role='user', content=' ')]), 'unit-model'),
                 (LLMRequest(messages=[ChatMessage(role='user', content='x'*100001)]), 'unit-model'),
                 (request(max_output_tokens=15), 'unit-model'), (request(max_output_tokens=16385), 'unit-model'),
                 (request(temperature=float('nan')), 'unit-model')]
        for req, model in cases:
            with self.assertRaises(DomainValidationError):
                await p.complete(req, model=model)
        self.assertEqual(calls, [])

    async def test_http_errors_are_sanitized_and_not_retried(self):
        for status, expected in [(401, IntegrationNotConfiguredError), (403, IntegrationNotConfiguredError),
                                 (429, RateLimitExceededError), (500, IntegrationError),
                                 (400, DomainValidationError), (302, DomainValidationError)]:
            calls = []
            def handle(req):
                calls.append(req)
                return httpx.Response(status, text='unit-sensitive-key private prompt', headers={'location': 'https://elsewhere.invalid/'})
            with self.subTest(status=status), self.assertRaises(expected) as caught:
                await provider(handle).complete(request(), model='unit-model')
            self.assertNotIn('unit-sensitive-key', str(caught.exception))
            self.assertNotIn('private prompt', str(caught.exception))
            self.assertEqual(len(calls), 1)

    async def test_timeout_is_sanitized(self):
        def handle(req):
            raise httpx.ReadTimeout('unit-sensitive-key private prompt', request=req)
        with self.assertRaises(IntegrationError) as caught:
            await provider(handle).complete(request(), model='unit-model')
        self.assertEqual(str(caught.exception), 'OpenAI connection failed or timed out.')
        self.assertTrue(caught.exception.__suppress_context__)

    async def test_bad_json_content_type_and_size_rejected(self):
        for response in [httpx.Response(200, content=b'{', headers={'content-type': 'application/json'}),
                         httpx.Response(200, text='not json'),
                         httpx.Response(200, content=b'x'*(2*1024*1024+1), headers={'content-type': 'application/json'})]:
            with self.assertRaises(IntegrationError):
                await provider(lambda req: response).complete(request(), model='unit-model')

    async def test_incomplete_and_failed_responses_rejected(self):
        for status in ['incomplete', 'failed', 'queued', 'in_progress', None]:
            body = success(); body['status'] = status
            with self.subTest(status=status), self.assertRaises(IntegrationError):
                await provider(lambda req: httpx.Response(200, json=body)).complete(request(), model='unit-model')

    async def test_refusals_tool_calls_and_empty_text_rejected(self):
        for output in [[], [{'type': 'function_call', 'name': 'send_message'}],
                       [{'type': 'message', 'role': 'assistant', 'status': 'completed', 'content': [{'type': 'refusal', 'refusal': 'private refusal'}]}],
                       [{'type': 'message', 'role': 'assistant', 'status': 'completed', 'content': [{'type': 'output_text', 'text': ' '}]}]]:
            body = success(); body['output'] = output
            with self.assertRaises(IntegrationError):
                await provider(lambda req: httpx.Response(200, json=body)).complete(request(), model='unit-model')

    async def test_invalid_usage_not_fabricated(self):
        for usage in [None, {}, {'input_tokens': True, 'output_tokens': 3}, {'input_tokens': -1, 'output_tokens': 3}, {'input_tokens': '12', 'output_tokens': 3}]:
            body = success(); body['usage'] = usage
            with self.assertRaises(IntegrationError):
                await provider(lambda req: httpx.Response(200, json=body)).complete(request(), model='unit-model')

    async def test_malformed_shapes_and_error_rejected(self):
        bodies = [[], None, {**success(), 'error': {'message': 'private provider error'}},
                  {**success(), 'model': ''}, {**success(), 'output': [None]},
                  {**success(), 'output': [{'type': 'message', 'role': 'user', 'content': []}]}]
        for body in bodies:
            with self.assertRaises(IntegrationError) as caught:
                await provider(lambda req: httpx.Response(200, json=body)).complete(request(), model='unit-model')
            self.assertNotIn('private provider error', str(caught.exception))

    async def test_reasoning_not_exposed_and_text_order_preserved(self):
        body = success()
        body['output'].insert(0, {'type': 'reasoning', 'summary': 'private reasoning'})
        body['output'][1]['content'] = [{'type': 'output_text', 'text': 'First '}, {'type': 'output_text', 'text': 'ثاني'}]
        result = await provider(lambda req: httpx.Response(200, json=body)).complete(request(), model='unit-model')
        self.assertEqual(result.text, 'First ثاني')

    async def test_transport_closed_on_success_and_failure(self):
        class Transport(httpx.MockTransport):
            closed = False
            async def aclose(self):
                self.closed = True
        for status in [200, 500]:
            transport = Transport(lambda req: httpx.Response(status, json=success()))
            p = OpenAIResponsesProvider(SecretStr('unit-key'), transport=transport)
            try:
                await p.complete(request(), model='unit-model')
            except IntegrationError:
                pass
            self.assertTrue(transport.closed)

    async def test_cancellation_propagates(self):
        async def handle(req):
            raise asyncio.CancelledError
        with self.assertRaises(asyncio.CancelledError):
            await provider(handle).complete(request(), model='unit-model')

    async def test_provider_contract_and_no_external_or_held_execution(self):
        p = provider(lambda req: httpx.Response(200, json=success()))
        self.assertIsInstance(p, LLMProvider)
        self.assertNotIn('unit-sensitive-key', repr(p))
        original = request(); snapshot = copy.deepcopy(original.model_dump())
        result = await p.complete(original, model='unit-model')
        self.assertEqual(original.model_dump(), snapshot)
        self.assertEqual(result.usage.input_tokens, 12)
        self.assertEqual(attempts, {'connections': 0, 'held_execution': 0})


if __name__ == '__main__':
    execution = unittest.main(verbosity=2, exit=False)
    if attempts != {'connections': 0, 'held_execution': 0}:
        print('FAIL: A forbidden connection or held-source execution was attempted.')
        sys.exit(1)
    sys.exit(0 if execution.result.wasSuccessful() else 1)
