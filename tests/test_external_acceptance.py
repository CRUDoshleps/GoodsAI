"""QA-006 harness integrity and real isolated CLI/HTTP execution; no catalogue data."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from goodsai.adversarial import case_errors
from goodsai.contracts import load_config
from goodsai.verify import Extractor
from scripts.release import external_acceptance as runner
from scripts.release.external_cases import generated_cases
from scripts.release.probe_http import listening_server


class ExternalAcceptanceTests(unittest.TestCase):
    def test_seed_is_reproducible_and_changes_facts_not_just_ids(self):
        a, b = generated_cases(20261020), generated_cases(20261021)
        self.assertEqual(a, generated_cases(20261020))
        self.assertNotEqual([c['input']['title'] for c in a], [c['input']['title'] for c in b])
        self.assertEqual(len(a), 16)
        self.assertEqual(len({c['id'] for c in a}), len(a))
        self.assertEqual(len({c['input']['sku_id'] for c in a}), len(a))
        self.assertEqual({c['input']['category_id'] for c in a}, {'761', '482', 'unseen-category'})
        for c in a:
            for attr in c['expected']['attributes'].values():
                if attr['evidence']:
                    e = attr['evidence']
                    self.assertEqual(c['input'][e['field']][e['start']:e['end']], e['text'])

    def test_shared_checker_rejects_wrong_values_and_silent_abstain_even_with_parity(self):
        case = generated_cases(20261020)[0]
        config = load_config()
        from goodsai.contracts import Product
        row = Extractor(config).predict(Product.from_dict(case['input']))
        self.assertEqual(case_errors(case, row, config), [])
        wrong = deepcopy(row)
        next(a for a in wrong['attributes'] if a['attribute'] == 'storage_gb')['value'] = '32'
        self.assertEqual(runner.comparable(wrong), runner.comparable(deepcopy(wrong)))
        self.assertIn('storage_gb.value', case_errors(case, wrong, config))
        missing = deepcopy(row)
        for a in missing['attributes']:
            a.update(value=None, unit=None, confidence=None, evidence=None,
                     decision='abstain', reason_codes=['not_found_by_rules'])
        self.assertTrue(case_errors(case, missing, config))
        wrong = deepcopy(row)
        next(a for a in wrong['attributes'] if a['attribute'] == 'model')['evidence']['start'] += 1
        self.assertIn('prediction_contract_or_evidence', case_errors(case, wrong, config))
        self.assertTrue(case_errors(case, {}, config))

    def test_strict_status_never_exempts_known_issues_or_execution_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'run'
            with patch.object(runner, 'destination', return_value=output):
                report = runner.run(output, 20261020)
                before = {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()}
                with self.assertRaises(FileExistsError):
                    runner.run(output, 20261020)
            self.assertEqual(before, {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()})
            self.assertEqual(report['case_checks_total'], 74)
            self.assertEqual(report['checks_total'], 83)
            self.assertTrue(all(c['passed'] for c in report['stages']), report['stages'])
            failures = [c for c in report['cases'] if not c['passed']]
            self.assertTrue(all(c['known_issue'] in {15, 21} for c in failures), failures)
            self.assertEqual(report['status'], 'failed' if failures else 'passed')
            self.assertEqual(runner.result_code(report), 1 if failures else 0)
            # A future runtime fix may remove failures, but cannot remove the cases.
            self.assertTrue(any(c['id'] == 'qa-001/brand_is_not_color' for c in report['cases']))
            self.assertEqual({c['transport'] for c in report['cases']}, {'cli', 'http'})
            self.assertIsNotNone(report['identity']['git_commit'])
            self.assertEqual(report['llm_calls'], 0)
            for filename, digest in report['files'].items():
                self.assertEqual(runner.sha(output / filename), digest)
            saved = json.loads((output / 'report.json').read_text(encoding='utf-8'))
            self.assertEqual(saved, report)

    def test_subprocess_timeout_is_error_without_private_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'run'
            with patch.object(runner, 'destination', return_value=output), \
                    patch.object(runner, 'command', side_effect=subprocess.TimeoutExpired('SECRET', 1, output=b'PRIVATE')):
                report = runner.run(output, 17)
            self.assertEqual(report['status'], 'error')
            self.assertEqual(runner.result_code(report), 2)
            self.assertEqual(report['error_kind'], 'TimeoutExpired')
            self.assertNotIn('SECRET', json.dumps(report))
            self.assertNotIn('PRIVATE', (output / 'report.md').read_text())

    def test_failed_server_readiness_always_reaps_its_process(self):
        process = unittest.mock.Mock()
        process.poll.return_value = None
        with patch('scripts.release.probe_http.subprocess.Popen', return_value=process), \
                patch('scripts.release.probe_http.time.monotonic', side_effect=[0, 31]):
            with self.assertRaisesRegex(RuntimeError, 'ready'):
                with listening_server('unused', '.', {}):
                    self.fail('not ready')
        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=10)


if __name__ == '__main__':
    unittest.main()
