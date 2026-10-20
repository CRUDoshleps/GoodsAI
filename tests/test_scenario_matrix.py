"""SPEC-002 evidence integrity, failure paths and actual external runtime execution."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from goodsai.config import load_config
from goodsai.contracts import Product
from goodsai.verify import Extractor
from goodsai.adversarial import case_errors
from scripts.release import scenario_matrix as matrix
from scripts.release.scenario_catalog import REQUIREMENTS, SCENARIOS, SUITES
from scripts.release.scenario_cases import policy_cases


class ScenarioMatrixTests(unittest.TestCase):
    def setUp(self):
        self.requirements = deepcopy(REQUIREMENTS)
        self.scenarios = deepcopy(SCENARIOS)
        self.cases = matrix.oracle(20261020)
        self.external = dict(status='passed', cases=[dict(id=c['id'], transport=t, passed=True)
            for c in self.cases for t in ('cli', 'http')],
            stages=[dict(name=s, passed=True) for s in sorted(matrix.STAGES - {'all_external_checks'})])
        total = len(self.external['cases']) + len(self.external['stages'])
        self.external.update(checks_passed=total, checks_total=total)
        self.suites = {name: dict(passed=True) for name in SUITES}

    def validate(self):
        return matrix.validate_catalog(self.requirements, self.scenarios, self.cases, load_config())

    def evaluate(self):
        return {r['id']: r for r in matrix.evaluate(self.requirements, self.scenarios,
                                                   self.external, self.suites, self.cases)}

    def test_catalog_has_stable_inventory_and_every_supported_attribute(self):
        self.validate()
        self.assertEqual(len(self.requirements), 29)
        self.assertEqual(len(self.scenarios), 29)
        self.assertEqual(len(self.cases), 46)
        rows = self.evaluate()
        self.assertEqual(sum(r['status'] == 'passed' for r in rows.values()), 17)
        self.assertEqual(rows['SCN-101']['status'], 'not_implemented')
        self.assertEqual(rows['SCN-104']['status'], 'not_verified')
        self.assertEqual(rows['SCN-201']['status'], 'unknown')

    def test_deleted_requirement_scenario_or_evidence_is_rejected(self):
        for kind in ['requirement', 'scenario', 'binding', 'oracle_attribute']:
            with self.subTest(kind=kind):
                self.setUp()
                if kind == 'requirement':
                    del self.requirements['REQ-002']
                elif kind == 'scenario':
                    del self.scenarios['SCN-002']
                elif kind == 'oracle_attribute':
                    del self.cases[0]['expected']['attributes']['model']
                else:
                    self.scenarios['SCN-002']['evidence'] = []
                with self.assertRaises(ValueError):
                    self.validate()

    def test_gap_cannot_hide_a_required_executable_scenario(self):
        self.scenarios['SCN-002'].update(state='not_verified', evidence=[], issues=[35], reason='skip')
        with self.assertRaisesRegex(ValueError, 'downgraded'):
            self.validate()

    def test_invalid_source_duplicate_and_unknown_driver_are_rejected(self):
        for kind in ['source', 'section', 'case', 'duplicate', 'source_kind', 'suite', 'stage']:
            with self.subTest(kind=kind):
                self.setUp()
                if kind == 'source':
                    self.requirements['REQ-001']['reference'] = '../unrelated.md'
                elif kind == 'section':
                    self.requirements['REQ-001']['section'] = 'Missing source section'
                elif kind == 'source_kind':
                    self.requirements['REQ-001']['source_kind'] = 'invented_official'
                elif kind == 'duplicate':
                    self.scenarios['SCN-002']['evidence'] *= 2
                else:
                    self.scenarios['SCN-002']['evidence'] = [dict(kind=kind, key='missing')]
                with self.assertRaises(ValueError):
                    self.validate()

    def test_weakened_oracle_and_wrong_evidence_are_rejected(self):
        case = self.cases[0]
        del case['expected']['attributes']['model']['value']
        with self.assertRaisesRegex(ValueError, 'Oracle must'):
            self.validate()
        self.setUp()
        self.cases[0]['expected']['attributes']['model']['evidence']['start'] += 1
        with self.assertRaisesRegex(ValueError, 'exact source'):
            self.validate()

    def test_missing_duplicate_failed_or_unmapped_checks_cannot_pass(self):
        for kind in ['missing', 'duplicate', 'failed', 'stage', 'unmapped']:
            with self.subTest(kind=kind):
                self.setUp()
                item = next(c for c in self.external['cases'] if c['id'] ==
                            ('generated/phone-title-2' if kind == 'unmapped' else 'generated/phone-title-0'))
                if kind in {'missing', 'unmapped'}:
                    self.external['cases'].remove(item)
                elif kind == 'duplicate':
                    self.external['cases'].append(item)
                elif kind == 'failed':
                    item['passed'] = False
                else:
                    self.external['stages'] = []
                self.assertEqual(self.evaluate()['SCN-014']['status'], 'failed')
                if kind in {'missing', 'duplicate', 'failed'}:
                    self.assertEqual(self.evaluate()['SCN-002']['status'], 'failed')

    def test_missing_offline_suite_stays_a_failure(self):
        del self.suites['llm_bounds']
        self.assertEqual(self.evaluate()['SCN-016']['status'], 'failed')

    def test_source_authored_facts_replay_and_wrong_value_does_not_pass(self):
        cases = policy_cases(20261020)
        self.assertEqual(cases, policy_cases(20261020))
        self.assertNotEqual([c['input'] for c in cases], [c['input'] for c in policy_cases(20261021)])
        case = cases[0]
        config = load_config()
        row = Extractor(config).predict(Product.from_dict(case['input']))
        self.assertEqual(case_errors(case, row, config), [])
        next(a for a in row['attributes'] if a['attribute'] == 'model')['value'] = 'Wrong'
        self.assertIn('model.value', case_errors(case, row, config))

    def test_real_matrix_verification_preserves_runs_and_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder).resolve() / 'matrix'
            with patch.object(matrix, 'destination', side_effect=lambda p: Path(p).absolute()), \
                    patch.object(matrix.external_acceptance, 'destination', side_effect=lambda p: Path(p).absolute()):
                report = matrix.run(output, 20261020)
                self.assertEqual(report['status'], 'passed')
                self.assertEqual(report['external_checks'], dict(passed=101, total=101))
                self.assertFalse(report['complete_case_evidence'])
                self.assertEqual(set(report['positive_attribute_evidence']), {'761', '482'})
                self.assertTrue(all(ids for attrs in report['positive_attribute_evidence'].values() for ids in attrs.values()))
                self.assertEqual(matrix.verify(output)['status'], 'verified')
                before = (output / 'report.json').read_bytes()
                with self.assertRaises(FileExistsError):
                    matrix.run(output, 20261020)
                self.assertEqual(before, (output / 'report.json').read_bytes())
                manifest = json.loads((output / 'scenario.manifest.json').read_text())
                self.assertFalse(manifest['final_six_artifact_delivery'])
                self.assertTrue(all(r['id'] for r in manifest['scenarios']))
                unexpected = output / 'unexpected.txt'
                unexpected.write_text('not inventoried', encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'inventory'):
                    matrix.verify(output)
                unexpected.unlink()
                (output / 'external/predictions.jsonl').write_text('tampered', encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                    matrix.verify(output)

    def test_interrupted_driver_keeps_error_report_gaps_and_safe_diagnostics(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder).resolve() / 'matrix'
            with patch.object(matrix, 'destination', return_value=output), \
                    patch.object(matrix.external_acceptance, 'run', side_effect=subprocess.TimeoutExpired('SECRET', 1, output=b'PRIVATE')):
                report = matrix.run(output, 17)
            self.assertEqual(report['status'], 'error')
            self.assertGreater(report['counts']['failed'], 0)
            self.assertEqual(report['counts']['unknown'], 1)
            self.assertNotIn('SECRET', json.dumps(report))
            self.assertNotIn('PRIVATE', (output / 'report.md').read_text())

    def test_offline_success_with_zero_tests_does_not_count_as_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            fake = subprocess.CompletedProcess([], 0, stdout=b'{"passed":true,"checks_run":0}')
            with patch.object(matrix.subprocess, 'run', return_value=fake):
                report = matrix.offline_suite('verifier', Path(folder), {})
            self.assertFalse(report['passed'])

    def test_cli_regression_and_execution_error_have_distinct_nonzero_codes(self):
        for status, code in [('failed', 1), ('error', 2)]:
            with self.subTest(status=status), patch.object(matrix, 'run', return_value=dict(status=status)):
                self.assertEqual(matrix.main(['--output-dir', 'unused']), code)


if __name__ == '__main__':
    unittest.main()
