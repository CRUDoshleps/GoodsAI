"""LLM-007 adversarial response validation; invented cards, no external calls."""
from copy import deepcopy
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

from goodsai.contracts import Product, load_config, validate_prediction
from goodsai.llm import (ExactCache, LLMExtractor, LLMSettings, OpenAICompatibleProvider,
                         ProviderError, ProviderResponse, cache_key, ground, has_signal, parse_proposals)
from goodsai.verify import Extractor
from test_llm import FakeProvider, PHONE, Response, answer, attrs, http_error
from scripts.release.clean_run import verify_pair
from scripts.release.probe_http import listening_server, request_json


class ResponseValidationTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()
        self.baseline = Extractor(self.config).predict(PHONE, 'same')
        self.gaps = [a['attribute'] for a in self.baseline['attributes']
                     if a['reason_codes'] == ['not_found_by_rules'] and has_signal(PHONE, a['attribute'], self.config)]

    def check_preserved(self, row):
        validate_prediction(row, self.config, PHONE)
        for expected in self.baseline['attributes']:
            if expected['attribute'] not in self.gaps:
                self.assertEqual(attrs(row)[expected['attribute']], expected)

    def run_proposals(self, proposals, cached):
        with tempfile.TemporaryDirectory() as folder:
            settings = LLMSettings(model='fake-model', cache_dir=Path(folder) if cached else None)
            provider = FakeProvider(json.dumps({'attributes': proposals}, ensure_ascii=False))
            if cached:
                ExactCache(Path(folder)).put(cache_key(PHONE, self.gaps, self.config, settings), proposals, {})
            extractor = LLMExtractor(self.config, provider, settings)
            row = extractor.predict(PHONE, 'same')
            self.check_preserved(row)
            self.assertEqual(provider.calls, 0 if cached else 1)
            self.assertEqual(extractor.report()['cache_hits'], int(cached))
            return row, extractor.report()

    def test_non_string_attribute_is_rejected_before_membership_fresh_and_cached(self):
        for value in ([], {}, None, True, False, 7, 1.5, ''):
            for cached in (False, True):
                with self.subTest(attribute=value, cached=cached):
                    row, report = self.run_proposals([{'attribute': value, 'value': 'Zorion', 'quote': 'Zorion'}], cached)
                    self.assertEqual(report['rejected'], {'llm_bad_types': 1})
                    for name in self.gaps:
                        self.assertEqual(attrs(row)[name]['reason_codes'], ['not_found_by_rules', 'llm_bad_types'])
                        self.assertIsNone(attrs(row)[name]['value'])

    def test_bad_value_quote_and_elements_fresh_and_cached(self):
        proposals = [None, [], True, 0, 'untrusted', {},
                     {'attribute': 'brand', 'value': 'Zorion'},
                     {'attribute': 'brand', 'value': 'Zorion', 'quote': 'Zorion', 'extra': 'untrusted'}]
        for value in ([], {}, True, False):
            proposals.append({'attribute': 'brand', 'value': value, 'quote': 'Zorion'})
        for quote in ([], {}, None, True, 5):
            proposals.append({'attribute': 'brand', 'value': 'Zorion', 'quote': quote})
            proposals.append({'attribute': 'brand', 'value': None, 'quote': quote})
        # value=null, quote=null is an explicit abstention, per the existing prompt.
        proposals = [p for p in proposals if p != {'attribute': 'brand', 'value': None, 'quote': None}]
        for item in proposals:
            for cached in (False, True):
                with self.subTest(proposal=item, cached=cached):
                    row, report = self.run_proposals([item], cached)
                    reason = next(iter(report['rejected']))
                    self.assertIn(reason, ('llm_bad_types', 'llm_unknown_field'))
                    self.assertIn(reason, attrs(row)['brand']['reason_codes'])
                    self.assertIsNone(attrs(row)['brand']['value'])

    def test_mixed_valid_invalid_and_identical_duplicates_keep_verified_candidate(self):
        valid = {'attribute': 'brand', 'value': 'Zorion', 'quote': 'Zorion'}
        proposals = [{'attribute': [], 'value': 'Zorion', 'quote': 'Zorion'},
                     {'attribute': 'brand', 'value': {}, 'quote': 'Zorion'},
                     {'attribute': 'weight_g', 'value': '100', 'quote': 'Zorion'},
                     {'attribute': 'color', 'value': 'white', 'quote': 'Zorion'},
                     valid, deepcopy(valid)]
        for cached in (False, True):
            row, report = self.run_proposals(proposals, cached)
            self.assertEqual((attrs(row)['brand']['value'], attrs(row)['brand']['decision']), ('Zorion', 'review'))
            self.assertEqual(attrs(row)['brand']['reason_codes'], [])
            self.assertEqual(report['accepted'], 1)
            self.assertEqual(report['rejected'], {'llm_bad_types': 2, 'llm_unknown_attribute': 2})

    def test_conflicting_valid_duplicates_still_abstain(self):
        # Both values have exact evidence, but no arbitrary winner is allowed.
        proposals = [{'attribute': 'brand', 'value': name, 'quote': name} for name in ('Zorion', 'QX-900')]
        for cached in (False, True):
            row, _ = self.run_proposals(proposals, cached)
            self.assertIsNone(attrs(row)['brand']['value'])
            self.assertIn('conflicting_llm_evidence', attrs(row)['brand']['reason_codes'])

    def test_null_abstention_and_ground_public_entrypoint_are_safe(self):
        for cached in (False, True):
            row, report = self.run_proposals([{'attribute': 'brand', 'value': None, 'quote': None}], cached)
            self.assertIn('llm_not_found', attrs(row)['brand']['reason_codes'])
            self.assertEqual(report['rejected'], {})
        for value in (float('inf'), float('-inf'), float('nan')):
            self.assertEqual(ground(PHONE, 'brand', value, 'Zorion', self.config), (None, 'llm_bad_types'))
        self.assertEqual(ground(PHONE, [], 'Zorion', 'Zorion', self.config), (None, 'llm_bad_types'))

    def test_malformed_top_level_non_json_and_duplicate_keys_fail_closed(self):
        bad = ['', 'null', '[]', 'true', '1', '{"attributes":null}', '{"attributes":{}}',
               '{"attributes":[],"extra":1}', '{"attributes":[],"attributes":[]}',
               '{"attributes":[{"attribute":"brand","attribute":[],"value":"Zorion","quote":"Zorion"}]}',
               '{"attributes":[NaN]}', '[' * 1100 + '0' + ']' * 1100]
        for payload in bad:
            with self.subTest(payload=payload[:80]):
                extractor = LLMExtractor(self.config, FakeProvider(payload), LLMSettings(model='m'))
                row = extractor.predict(PHONE, 'same')
                self.check_preserved(row)
                self.assertIn('llm_malformed_json', attrs(row)['brand']['reason_codes'])
        for payload in (None, [], {}, True, 1):
            with self.assertRaises(ProviderError):
                parse_proposals(payload)

    def test_corrupt_cache_envelope_is_a_miss_not_a_crash(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = LLMSettings(model='m', cache_dir=Path(folder))
            cache = ExactCache(Path(folder))
            key = cache_key(PHONE, self.gaps, self.config, settings)
            cache.put(key, [], {})
            path = next(Path(folder).rglob('*.json'))
            entry = json.loads(path.read_text(encoding='utf-8'))
            for proposals in (None, {}, True, 'untrusted'):
                altered = entry | {'proposals': proposals}
                path.write_text(json.dumps(altered), encoding='utf-8')
                provider = FakeProvider(answer(('brand', 'Zorion', 'Zorion')))
                row = LLMExtractor(self.config, provider, settings).predict(PHONE, 'same')
                self.assertEqual((provider.calls, attrs(row)['brand']['value']), (1, 'Zorion'))
            for raw in ('[' * 1100 + '0' + ']' * 1100, '{"x":NaN}', '{"key":1,"key":2}'):
                path.write_text(raw, encoding='utf-8')
                self.assertIsNone(cache.get(key))

    def test_invalid_provider_metadata_cannot_break_accounting(self):
        for kwargs in ({'prompt_tokens': []}, {'completion_tokens': True}, {'model': {}},
                       {'attempts': '1'}, {'content': None}, {'prompt_tokens': -1}):
            with self.subTest(metadata=kwargs):
                class Provider:
                    def complete(self, *_):
                        return ProviderResponse(**({'content': answer()} | kwargs))
                extractor = LLMExtractor(self.config, Provider(), LLMSettings(model='m'))
                row = extractor.predict(PHONE, 'same')
                self.check_preserved(row)
                self.assertIn('llm_malformed_response', attrs(row)['brand']['reason_codes'])

    def test_interrupts_and_unexpected_programming_errors_are_not_swallowed(self):
        for error in (KeyboardInterrupt, SystemExit, RuntimeError):
            class Provider:
                def complete(self, *_):
                    raise error('do not swallow')
            with self.assertRaises(error):
                LLMExtractor(self.config, Provider(), LLMSettings(model='m')).predict(PHONE)


class GatewayValidationTests(unittest.TestCase):
    def test_envelope_types_usage_and_json_fail_without_retry_or_leak(self):
        good = {'model': 'stub', 'choices': [{'message': {'content': answer()}}],
                'usage': {'prompt_tokens': 10, 'completion_tokens': 2}}
        bad = [None, [], True, 5, {}, {'choices': {}}, {'choices': [None]},
               {'choices': [{'message': []}]}, {'choices': [{'message': {'content': None}}]}]
        for usage in ([], '', False, 4):
            bad.append(good | {'usage': usage})
        for value in (True, -1, '10', [], {}, None, 1.5, float('inf')):
            bad.append(good | {'usage': {'prompt_tokens': value}})
            bad.append(good | {'usage': {'completion_tokens': value}})
        for model in ([], {}, True, 4, 'x' * 201):
            bad.append(good | {'model': model})
        bodies = [json.dumps(b).encode() for b in bad] + [b'not-json', b'\xff',
                  b'{"choices":[],"choices":[]}', b'[' * 1100 + b'0' + b']' * 1100]
        for body in bodies:
            calls = []
            def opener(*args, **kwargs):
                calls.append(1)
                return Response(body)
            provider = OpenAICompatibleProvider('http://127.0.0.1/v1', 'secret-sentinel',
                                                 LLMSettings(model='m'), opener=opener)
            with self.subTest(body=body[:60]), self.assertRaises(ProviderError) as caught:
                provider.complete([], 256)
            self.assertEqual(str(caught.exception), 'llm_malformed_response')
            self.assertEqual(len(calls), 1)
            self.assertNotIn('secret-sentinel', repr(caught.exception))

    def test_optional_usage_and_model_and_retry_accounting(self):
        for usage in ({}, None):
            payload = {'choices': [{'message': {'content': answer()}}], 'usage': usage}
            provider = OpenAICompatibleProvider('http://127.0.0.1/v1', 'stub', LLMSettings(model='m'),
                                                 opener=lambda *a, **k: Response(json.dumps(payload).encode()))
            response = provider.complete([], 256)
            self.assertEqual((response.prompt_tokens, response.completion_tokens, response.model), (0, 0, None))
        events = iter([http_error(502), Response(b'{"choices":[{"message":{"content":null}}]}')])
        def opener(*args, **kwargs):
            event = next(events)
            if isinstance(event, Exception):
                raise event
            return event
        provider = OpenAICompatibleProvider('http://127.0.0.1/v1', 'stub', LLMSettings(model='m'),
                                             sleep=lambda _: None, opener=opener)
        with self.assertRaises(ProviderError) as caught:
            provider.complete([], 256)
        self.assertEqual(caught.exception.attempts, 2)


@contextmanager
def local_gateway(envelopes):
    """Real transport, but only synthetic responses on an ephemeral loopback port."""
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Never log Authorization or request/card text.

        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            index = len(calls)
            calls.append(self.path)
            body = json.dumps(envelopes[index % len(envelopes)], ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f'http://127.0.0.1:{server.server_port}/v1', calls
        finally:
            server.shutdown()
            thread.join(timeout=5)


class MalformedTransportTests(unittest.TestCase):
    def test_real_cli_batch_http_and_cache_replay_preserve_rules_and_continue(self):
        try:
            import uvicorn  # noqa: F401 - required only for the optional HTTP transport.
        except ImportError:
            self.skipTest('serve extras are not installed')
        config = load_config()
        invalid = {'attribute': [], 'value': 'untrusted-sentinel', 'quote': 'untrusted-sentinel'}
        valid = {'attribute': 'brand', 'value': 'Zorion', 'quote': 'Zorion'}
        def envelope(items):
            return {'choices': [{'message': {'content': json.dumps({'attributes': items})}}],
                    'usage': {'prompt_tokens': 10, 'completion_tokens': 5}, 'model': 'local-stub'}
        events = [envelope([invalid]), envelope([invalid, valid]), {'choices': []}, envelope([valid])]
        root = Path(__file__).resolve().parents[1]
        baseline = attrs(Extractor(config).predict(PHONE))
        rules_fields = {k: v for k, v in baseline.items() if v['value'] is not None}
        with tempfile.TemporaryDirectory() as folder, local_gateway(events) as (url, calls):
            work = Path(folder)
            inputs = [PHONE.as_dict() | {'sku_id': f'synthetic-{i}'} for i in range(4)]
            (work / 'input.jsonl').write_text(''.join(json.dumps(p, ensure_ascii=False) + '\n' for p in inputs),
                                             encoding='utf-8')
            env = {k: v for k, v in os.environ.items() if not k.startswith(('GOODSAI_', 'OPENAI_', 'PYTHON'))}
            env.update(PYTHONUTF8='1', PYTHONPATH=str(root / 'src'), NO_PROXY='127.0.0.1,localhost',
                       GOODSAI_LLM_BASE_URL=url, GOODSAI_LLM_API_KEY='fake-key-sentinel',
                       GOODSAI_LLM_MODEL='local-stub', GOODSAI_LLM_ENABLED='1',
                       GOODSAI_LLM_BUDGET_FILE=str(work / 'api-ledger.json'))
            command = [sys.executable, '-m', 'goodsai.cli', 'predict', '--input', str(work / 'input.jsonl'),
                       '--output', str(work / 'predictions.jsonl'), '--llm', '--llm-model', 'local-stub',
                       '--llm-budget-file', str(work / 'cli-ledger.json')]
            result = subprocess.run(command, cwd=root, env=env, capture_output=True, timeout=40)
            self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8'))
            self.assertEqual(len(calls), 4)
            verify_pair(work)
            rows = [json.loads(line) for line in (work / 'predictions.jsonl').read_text(encoding='utf-8').splitlines()]
            manifest_text = (work / 'predictions.manifest.json').read_text(encoding='utf-8')
            report = json.loads(manifest_text)
            self.assertEqual(report['rows'], 4)
            self.assertEqual(report['llm']['rejected'], {'llm_bad_types': 2})
            self.assertEqual(report['llm']['failures'], {'llm_malformed_response': 1})
            self.assertEqual(report['llm']['accepted'], 2)
            for marker in ('fake-key-sentinel', 'untrusted-sentinel', 'Zorion', url):
                self.assertNotIn(marker, manifest_text + result.stdout.decode('utf-8') + result.stderr.decode('utf-8'))
            with listening_server(sys.executable, root, env) as (base, process):
                http_rows = []
                for source in inputs:
                    status, row, _ = request_json(base, '/predict', json.dumps(source).encode())
                    self.assertEqual(status, 200)  # In particular, no prediction_failed/500.
                    http_rows.append(row)
                status, health, _ = request_json(base, '/health')
                self.assertEqual((status, health['llm']['calls']), (200, 4))
                self.assertNotIn('fake-key-sentinel', json.dumps(health))
            self.assertIsNotNone(process.poll())
            self.assertEqual(len(calls), 8)
            for i, (cli_row, http_row) in enumerate(zip(rows, http_rows)):
                product = Product.from_dict(inputs[i])
                validate_prediction(cli_row, config, product)
                validate_prediction(http_row, config, product)
                self.assertEqual({k: v for k, v in cli_row.items() if k != 'run_id'},
                                 {k: v for k, v in http_row.items() if k != 'run_id'})
                for name, expected in rules_fields.items():
                    self.assertEqual(attrs(cli_row)[name], expected)
                if i in (1, 3):
                    self.assertEqual(attrs(cli_row)['brand']['value'], 'Zorion')
                else:
                    self.assertEqual(attrs(cli_row)['brand']['decision'], 'abstain')
                    self.assertIn('llm_bad_types' if i == 0 else 'llm_malformed_response',
                                  attrs(cli_row)['brand']['reason_codes'])

            # A poisoned parsed cache must take the same guard without a provider call.
            cache_root = work / 'cache'
            settings = LLMSettings(model='local-stub', cache_dir=cache_root)
            gaps = [k for k, v in baseline.items() if v['reason_codes'] == ['not_found_by_rules']
                    and has_signal(PHONE, k, config)]
            ExactCache(cache_root).put(cache_key(PHONE, gaps, config, settings), [invalid], {})
            result = subprocess.run(command + ['--llm-cache-dir', str(cache_root)], cwd=root, env=env,
                                    capture_output=True, timeout=40)
            self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8'))
            verify_pair(work)
            cached_manifest = json.loads((work / 'predictions.manifest.json').read_text(encoding='utf-8'))
            self.assertEqual((cached_manifest['llm_calls'], cached_manifest['llm']['cache_hits'], len(calls)), (0, 4, 8))
            self.assertEqual(cached_manifest['llm']['rejected'], {'llm_bad_types': 4})
