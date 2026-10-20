"""CONF-002 effective policy, safe precedence and entry-point parity; synthetic only."""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from dataclasses import asdict
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from goodsai import cli
from goodsai.config import load_config, validate_config
from goodsai.llm import LLMSettings
from goodsai.policy import (ENV_FIELDS, llm_settings, policy_hash, resolve_runtime_policy, runtime_metadata)
from scripts.release.clean_run import verify_pair
from scripts.release.probe_http import listening_server, request_json
from test_llm import PHONE, FakeProvider, answer, attrs

ROOT = Path(__file__).resolve().parents[1]


def clean_env(**values):
    env = {k: v for k, v in os.environ.items() if not k.startswith(('GOODSAI_', 'OPENAI_'))}
    return env | values


class RuntimePolicyTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()

    def test_old_v1_profile_completion_is_deterministic_and_independent(self):
        old = deepcopy(self.config)
        del old['runtime']['llm']
        del old['runtime']['review_threshold']
        self.assertEqual(validate_config(old), self.config)
        old['runtime']['llm'] = {'model': None}
        with self.assertRaises(ValueError):
            validate_config(old)  # Present means complete, never silently default a typo.

    def test_profile_environment_and_explicit_precedence(self):
        self.config['runtime']['llm'].update(model='profile-model', timeout_seconds=21, max_calls=7,
                                           json_mode=True)
        env = {'GOODSAI_LLM_ENABLED': '1', 'GOODSAI_LLM_MODEL': 'env-model', 'GOODSAI_LLM_MAX_CALLS': '6'}
        policy = resolve_runtime_policy(self.config, environ=env,
                                         overrides={'model': 'cli-model', 'max_calls': None, 'json_mode': False})
        self.assertTrue(policy['llm_enabled'])
        self.assertEqual((policy['llm']['model'], policy['llm']['max_calls'], policy['llm']['timeout_seconds'],
                          policy['llm']['json_mode']), ('cli-model', 6, 21, False))
        self.assertEqual(self.config['runtime']['llm']['model'], 'profile-model')
        self.assertFalse(resolve_runtime_policy(self.config, enabled=False, environ=env)['llm_enabled'])
        self.assertFalse(resolve_runtime_policy(self.config, environ={})['llm_enabled'])

    def test_all_recognized_environment_fields_are_used_and_validated(self):
        env = {'GOODSAI_LLM_MODEL':'stub', 'GOODSAI_LLM_MAX_CALLS':'5',
               'GOODSAI_LLM_DAILY_MAX_CALLS':'15', 'GOODSAI_LLM_TIMEOUT':'12.5',
               'GOODSAI_LLM_ATTEMPTS':'2', 'GOODSAI_LLM_MAX_TOKENS':'777',
               'GOODSAI_LLM_CONCURRENCY':'1', 'GOODSAI_LLM_CIRCUIT_BREAKER':'3',
               'GOODSAI_LLM_JSON_MODE':'true', 'GOODSAI_LLM_PRICE_INPUT_PER_1K':'0.2',
               'GOODSAI_LLM_PRICE_OUTPUT_PER_1K':'0.7', 'GOODSAI_LLM_CACHE_DIR':'outputs/local-cache',
               'GOODSAI_LLM_BUDGET_FILE':'outputs/local-ledger.json', 'GOODSAI_LLM_ENABLED':'true',
               'GOODSAI_LLM_MODEL_REVISION':'revision', 'GOODSAI_LLM_CACHE_NAMESPACE':'synthetic',
               'GOODSAI_LLM_CACHE_TTL':'600'}
        policy = resolve_runtime_policy(self.config, environ=env)
        settings = llm_settings(policy)
        for key, (_, kind) in ENV_FIELDS.items():
            broken = env | {key: '' if kind in (str, bool) else 'not-a-number-secret'}
            with self.subTest(key=key), self.assertRaises(ValueError) as caught:
                resolve_runtime_policy(self.config, environ=broken)
            self.assertNotIn('not-a-number-secret', str(caught.exception))
        self.assertEqual((settings.max_tokens, settings.timeout_seconds, settings.price_output_per_1k), (777, 12.5, 0.7))
        self.assertEqual(settings.budget_ledger, Path('outputs/local-ledger.json'))

    def test_invalid_profile_fields_and_policy_cannot_activate_acceptance(self):
        invalid = {'timeout_seconds': [True, '1', None, float('nan'), float('inf'), 0, 301],
                   'max_tokens': [True, 100.5, 63, 8193], 'concurrency': [False, 0, 9],
                   'circuit_breaker': [True, 0, 101], 'max_attempts': [0, 6, 2.5],
                   'model': [False, [], '', ' spaced ', 'x' * 201], 'json_mode': [0, 'false', None],
                   'max_calls': [True, -1, '1'], 'daily_max_calls': [False, -1, 1.5],
                   'price_input_per_1k': [False, -1, '0.1', float('nan')],
                   'price_output_per_1k': [True, float('inf')], 'cache_dir': ['', [], False],
                   'budget_ledger': ['', {}, True]}
        for key, values in invalid.items():
            for value in values:
                config = deepcopy(self.config)
                config['runtime']['llm'][key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    validate_config(config)
        for threshold in (0, 0.5, 1, True, '0.8'):
            config = deepcopy(self.config)
            config['runtime']['review_threshold'] = threshold
            with self.assertRaises(ValueError):
                validate_config(config)
        for key in ('api_key', 'base_url', 'typo'):
            config = deepcopy(self.config)
            config['runtime']['llm'][key] = 'must-not-appear'
            with self.assertRaises(ValueError) as caught:
                validate_config(config)
            self.assertNotIn('must-not-appear', str(caught.exception))

    def test_invalid_environment_and_missing_model_or_ledger_fail_even_when_disabled(self):
        for env in ({'GOODSAI_LLM_TIMEOUT': 'NaN'}, {'GOODSAI_LLM_ENABLED': 'maybe'},
                    {'GOODSAI_LLM_TIMOUT': 'secret'}, {'GOODSAI_LLM_MAX_TOKENS': '1.5'}):
            with self.assertRaises(ValueError):
                resolve_runtime_policy(self.config, enabled=False, environ=env)
        with self.assertRaises(ValueError):
            resolve_runtime_policy(self.config, enabled=True, environ={})
        self.config['runtime']['llm'].update(model='stub', budget_ledger=None)
        with self.assertRaises(ValueError):
            resolve_runtime_policy(self.config, enabled=True, environ={})

    def test_actual_effective_hash_tracks_overrides_but_not_credentials(self):
        env = {'GOODSAI_LLM_MODEL': 'stub', 'GOODSAI_LLM_ENABLED': '1',
               'GOODSAI_LLM_API_KEY': 'fake-secret', 'GOODSAI_LLM_BASE_URL': 'https://private.invalid/v1'}
        policy = resolve_runtime_policy(self.config, environ=env)
        meta = runtime_metadata(self.config, policy)
        self.assertEqual(meta['runtime_policy_sha256'], policy_hash(meta['runtime_policy']))
        self.assertEqual(meta['effective_config_sha256'], policy_hash(meta['effective_config']))
        self.assertEqual(meta, runtime_metadata(self.config, resolve_runtime_policy(self.config,
                           environ=env | {'GOODSAI_LLM_API_KEY': 'another-secret'})))
        for key, value in [('timeout_seconds', 11), ('price_input_per_1k', 0.5), ('max_calls', 1)]:
            changed = runtime_metadata(self.config, resolve_runtime_policy(self.config, environ=env,
                                           overrides={key: value}))
            self.assertNotEqual(changed['effective_config_sha256'], meta['effective_config_sha256'])
        for secret in ('fake-secret', 'private.invalid', 'API_KEY', 'BASE_URL'):
            self.assertNotIn(secret, json.dumps(meta))

    def test_low_level_settings_share_validation_and_defaults(self):
        policy = resolve_runtime_policy(self.config, enabled=True, overrides={'model': 'stub'}, environ={})
        expected = LLMSettings(model='stub', budget_ledger=Path(policy['llm']['budget_ledger']))
        self.assertEqual(asdict(llm_settings(policy)), asdict(expected))
        for kwargs in ({'timeout_seconds': True}, {'max_tokens': 100.5}, {'json_mode': 1},
                       {'price_input_per_1k': True}, {'circuit_breaker': 0}):
            with self.assertRaises(ValueError):
                LLMSettings(model='stub', **kwargs)


class RuntimeEntryPointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = load_config()
        self.config['runtime']['llm'].update(model='fake-model', timeout_seconds=19, max_tokens=512,
                   max_calls=4, max_attempts=1, concurrency=1, circuit_breaker=3,
                   price_input_per_1k=0.1, price_output_per_1k=0.2,
                   budget_ledger=str(self.root / 'budget.json'))
        self.path = self.root / 'profile.json'
        self.path.write_text(json.dumps(self.config, ensure_ascii=False), encoding='utf-8')
        self.input = self.root / 'input.jsonl'
        self.input.write_text(json.dumps(PHONE.as_dict(), ensure_ascii=False) + '\n', encoding='utf-8')
        self.args = ['--config', str(self.path), 'predict', '--input', str(self.input),
                     '--output', str(self.root / 'predictions.jsonl')]

    def run_cli(self, options=()):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(self.args + list(options))
        return code, out.getvalue(), err.getvalue()

    def test_cli_api_use_identical_effective_policy_and_results(self):
        from fastapi.testclient import TestClient
        from goodsai.api import create_app
        captured = []
        def factory(settings):
            captured.append(settings)
            return FakeProvider(answer(('brand', 'Zorion', 'Zorion')))
        env = clean_env(GOODSAI_LLM_ENABLED='1', GOODSAI_LLM_TIMEOUT='17',
                        GOODSAI_LLM_API_KEY='fake-key-sentinel', GOODSAI_LLM_BASE_URL='https://private.invalid/v1')
        with patch.dict(os.environ, env, clear=True), patch('goodsai.llm.provider_from_env', side_effect=factory):
            code, out, err = self.run_cli(['--llm'])
            self.assertEqual(code, 0, err)
            app = create_app(str(self.path))
            with TestClient(app) as client:
                response = client.post('/predict', json=PHONE.as_dict())
                health = client.get('/health').json()
        manifest = json.loads((self.root / 'predictions.manifest.json').read_text(encoding='utf-8'))
        verify_pair(self.root)
        self.assertEqual(manifest['effective_config'], app.state.goodsai_runtime['effective_config'])
        self.assertEqual(manifest['effective_config_sha256'], health['effective_config_sha256'])
        self.assertEqual(manifest['runtime_policy_sha256'], health['runtime_policy_sha256'])
        self.assertEqual(asdict(captured[0]), asdict(captured[1]))
        self.assertEqual((captured[0].timeout_seconds, captured[0].max_tokens, captured[0].max_attempts), (17, 512, 1))
        row = json.loads((self.root / 'predictions.jsonl').read_text(encoding='utf-8'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(attrs(row), attrs(response.json()))
        self.assertEqual(attrs(row)['brand']['decision'], 'review')
        self.assertEqual(manifest['llm']['cost_status'], 'priced')
        for secret in ('fake-key-sentinel', 'private.invalid'):
            self.assertNotIn(secret, out + err + json.dumps(health))

    def test_cli_overrides_zero_and_false_are_not_lost_to_defaults(self):
        provider = FakeProvider(AssertionError('budget zero must prevent calls'))
        with patch.dict(os.environ, clean_env(GOODSAI_LLM_JSON_MODE='true'), clear=True), \
             patch('goodsai.llm.provider_from_env', return_value=provider):
            code, _, err = self.run_cli(['--llm', '--llm-max-calls', '0', '--no-llm-json-mode'])
        self.assertEqual(code, 0, err)
        report = json.loads((self.root / 'predictions.manifest.json').read_text(encoding='utf-8'))
        self.assertEqual((report['runtime_policy']['llm']['max_calls'], report['runtime_policy']['llm']['json_mode'],
                          provider.calls), (0, False, 0))
        self.assertEqual(report['runtime_policy']['decisions']['review_threshold'], None)

    def test_invalid_policy_does_not_publish_or_start_api(self):
        from goodsai.api import create_app
        with patch.dict(os.environ, clean_env(), clear=True):
            self.assertEqual(self.run_cli()[0], 0)
        pair = [self.root / 'predictions.jsonl', self.root / 'predictions.manifest.json']
        before = [p.read_bytes() for p in pair]
        with patch.dict(os.environ, clean_env(GOODSAI_LLM_ATTEMPTS='secret-invalid-value'), clear=True), \
             patch('goodsai.llm.provider_from_env', side_effect=AssertionError('must fail before provider')):
            code, out, err = self.run_cli(['--llm'])
            self.assertEqual(code, 2)
            self.assertNotIn('secret-invalid-value', out + err)
            with self.assertRaises(ValueError):
                create_app(str(self.path))
        self.assertEqual([p.read_bytes() for p in pair], before)

    def test_profile_never_enables_llm_without_entry_point_opt_in_and_trace_cannot_raise_budget(self):
        provider = FakeProvider(AssertionError('must not be called'))
        with patch.dict(os.environ, clean_env(GOODSAI_LLM_ENABLED='1'), clear=True), \
             patch('goodsai.llm.provider_from_env', return_value=provider) as factory:
            self.assertEqual(self.run_cli()[0], 0)  # Environment cannot enable CLI --llm implicitly.
            factory.assert_not_called()
        self.config['runtime']['llm']['max_calls'] = 0
        self.path.write_text(json.dumps(self.config), encoding='utf-8')
        with patch.dict(os.environ, clean_env(), clear=True), \
             patch('goodsai.llm.provider_from_env', return_value=provider), \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code = cli.main(['--config', str(self.path), 'llm-trace', '--output', str(self.root / 'trace.json')])
        self.assertEqual((code, provider.calls), (3, 0))

    def test_production_example_real_cli_and_socket_api_rules_only(self):
        # Run the documented full profile with no model access or data dependencies.
        example = ROOT / 'configs/production.example.json'
        expected = load_config(example)
        env = clean_env(PYTHONUTF8='1', PYTHONPATH=str(ROOT / 'src'))
        result = subprocess.run([sys.executable, '-m', 'goodsai.cli', '--config', str(example), 'predict',
              '--input', str(self.input), '--output', str(self.root / 'predictions.jsonl')],
              env=env, cwd=ROOT, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8'))
        verify_pair(self.root)
        manifest = json.loads((self.root / 'predictions.manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['effective_config']['profile'], expected)
        rows = [json.loads(line) for line in (self.root / 'predictions.jsonl').read_text(encoding='utf-8').splitlines()]
        with listening_server(sys.executable, ROOT, env, ['--config', str(example)]) as (base, process):
            status, health, _ = request_json(base, '/health')
            self.assertEqual((status, health['effective_config_sha256']), (200, manifest['effective_config_sha256']))
            status, row, _ = request_json(base, '/predict', json.dumps(PHONE.as_dict()).encode())
            self.assertEqual((status, attrs(row)), (200, attrs(rows[0])))
        self.assertIsNotNone(process.poll())
