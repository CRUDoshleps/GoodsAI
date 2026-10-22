"""Offline acceptance audit must never promote a candidate or fabricate human labels."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from goodsai.contracts import Product, load_config
from goodsai.data import digest
from goodsai.silver_prepare import VERSION, assemble
from goodsai.verify import Extractor
from scripts.research import storage_shadow as shadow
from scripts.research.audit_splits import dump, write_rows
from scripts.research.human_gold import checked


def fixture(root, *, protected=False, target_leak=False):
    config = load_config()
    inputs = [
        Product('p1', '761', 'Смартфон Demo 8/128GB', None).as_dict(),
        Product('p2', '761', 'Смартфон Demo 8/128GB', None).as_dict(),
        Product('p3', '761', 'Смартфон Demo Q', 'Встроенная память 256 GB.').as_dict(),
        Product('k1', '482', 'Чайник Demo K', 'Мощность 2000 Вт.').as_dict(),
    ]
    members = {r['sku_id']: {'family_id': 'f1' if r['sku_id'] in {'p1', 'p2'} else r['sku_id'],
                            'split': 'development', 'quarantine_reasons': []} for r in inputs}
    catalog = {r['sku_id']: {'category_id': r['category_id'], 'params': []} for r in inputs}
    for sku, value in [('p1', '128'), ('p2', '64')]:
        catalog[sku]['params'] = [{'@name': 'Встроенная память (ROM)_search', '#text': value, '@unit': 'GB'}]
    inputs, references, metadata, _ = assemble(inputs, catalog, members, config)
    if protected:
        metadata[0]['original_split'] = 'test_reserved'
    if target_leak:
        inputs[0]['vendor'] = 'forbidden'
    bundle = root/'source'
    bundle.mkdir()
    for name, rows in [('input.jsonl', inputs), ('reference.jsonl', references), ('metadata.jsonl', metadata)]:
        write_rows(bundle/name, rows)
    for name in ['train.jsonl', 'support_review.blank.jsonl', 'llm_screening.input.jsonl']:
        write_rows(bundle/name, [])
    dump(bundle/'train.split.json', {})
    dump(bundle/'policy.json', {'config': config})
    dump(bundle/'manifest.json', {'version': VERSION, 'reference_kind': 'catalog_silver',
                                'protected_text_exported': False,
                                'artifacts': {p.name: digest(p) for p in bundle.iterdir()}})
    return bundle


def response_for(bundle):
    data = json.loads((bundle/'tasks.private.json').read_text(encoding='utf-8'))
    response = {k: data[k] for k in ['package_id', 'slot', 'reviewer_id']}
    response['attestation'] = {'human_only': True, 'candidate_checked': True, 'exposure_disclosed': True}
    response['tasks'] = [{'task_id': t['task_id'], 'attributes': [
        {'attribute': 'storage_gb', 'status': 'present', 'notes': '', **t['proposal']}]} for t in data['tasks']]
    return response


class StorageShadowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config()
        cls.extractor = Extractor(cls.config)

    def test_fixed_policy_selects_roles_and_unit_pairs_without_changing_review(self):
        for product in [Product('a', '761', 'Смартфон Example 8/128GB'),
                        Product('b', '761', 'Смартфон Example', 'Встроенная память 128 ГБ')]:
            prediction = self.extractor.predict(product)
            before = deepcopy(prediction)
            self.assertIsNone(shadow.select_reason(product, prediction, self.config))
            self.assertEqual(before, prediction)
            self.assertNotIn('auto_accept', json.dumps(prediction))

    def test_accessory_unknown_role_bad_unit_conflict_and_llm_are_not_selected(self):
        for product in [Product('a', '761', 'Чехол для смартфона Example 8/128GB'),
                        Product('b', '761', 'Смартфон Example 128 GB'),
                        Product('c', '761', 'Смартфон Example 8/128G'),
                        Product('d', '761', 'Смартфон Example 8/128GB', 'Встроенная память 64 ГБ')]:
            self.assertIsNotNone(shadow.select_reason(product, self.extractor.predict(product), self.config))
        product = Product('a', '761', 'Смартфон Example 8/128GB')
        prediction = self.extractor.predict(product)
        next(a for a in prediction['attributes'] if a['attribute'] == 'storage_gb')['method'] = 'llm'
        self.assertEqual(shadow.select_reason(product, prediction, self.config), 'outside_fixed_policy')

    def test_invalid_evidence_is_rejected_not_counted_as_coverage(self):
        product = Product('a', '761', 'Смартфон Example 8/128GB')
        prediction = self.extractor.predict(product)
        next(a for a in prediction['attributes'] if a['attribute'] == 'storage_gb')['evidence']['text'] = 'wrong'
        with self.assertRaisesRegex(ValueError, 'Evidence'):
            shadow.select_reason(product, prediction, self.config)

    def test_family_sampling_is_deterministic_and_exposure_propagates(self):
        metadata = {'a': {'family_id': 'f', 'exposed': False}, 'b': {'family_id': 'f', 'exposed': False},
                    'c': {'family_id': 'g', 'exposed': False}}
        rows = [{'sku_id': k} for k in metadata]
        first = shadow.family_sample(rows, metadata, set())[0]
        self.assertEqual(first, shadow.family_sample(list(reversed(rows)), metadata, set())[0])
        self.assertEqual(len(first), 2)
        self.assertEqual([r['sku_id'] for r in shadow.family_sample(rows, metadata, {'a'})[0]], ['c'])

    def test_exact_bound_handles_small_sample_errors_and_invalid_counts(self):
        self.assertIsNone(shadow.precision_lower(0, 0))
        self.assertAlmostEqual(shadow.precision_lower(100, 100), .9704869503929601)
        self.assertGreaterEqual(shadow.precision_lower(299, 299), .99)
        self.assertLess(shadow.precision_lower(298, 299), .99)
        self.assertAlmostEqual(shadow.precision_lower(1, 2), 1 - .95**.5)
        for args in [(True, 2), (3, 2), (1, -1)]:
            with self.assertRaises(ValueError):
                shadow.precision_lower(*args)

    def test_prepare_freezes_before_prediction_keeps_unknown_and_never_invents_gold(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, output = fixture(root), root/'audit'
            original_predict = shadow.predict
            def predict(*args, **kwargs):
                self.assertTrue((output/'freeze.json').is_file())
                self.assertFalse((output/'selection.private.jsonl').exists())
                return original_predict(*args, **kwargs)
            with patch.object(shadow, 'predict', side_effect=predict):
                report = shadow.prepare(source, output)
            self.assertEqual(report['shadow_selected_storage'], 3)
            self.assertEqual(report['catalog_selected'], {'selected': 3, 'tp': 1, 'fp': 1, 'unknown': 1, 'conflict': 0})
            self.assertEqual(report['audit_cards'], 2)
            self.assertIsNone(report['human_precision'])
            self.assertFalse(report['runtime_auto_accept'])
            self.assertFalse(report['test_reserved_opened'])
            checked(output, 'storage-shadow')
            data = json.loads((output/'tasks.private.json').read_text(encoding='utf-8'))
            self.assertTrue(all(t['attributes'][0]['status'] == 'unreviewed' for t in data['tasks']))
            self.assertTrue(all(t['attributes'][0]['value'] is None for t in data['tasks']))
            self.assertTrue(all(t['proposal']['value'] for t in data['tasks']))
            with self.assertRaisesRegex(ValueError, 'new_output_directory'):
                shadow.prepare(source, output)

    def test_protected_split_or_target_leak_fails_before_prediction(self):
        for flag in ['protected', 'target_leak']:
            with tempfile.TemporaryDirectory() as folder, patch.object(shadow, 'predict') as predict:
                root = Path(folder)
                source = fixture(root, **{flag: True})
                with self.assertRaisesRegex(ValueError, 'protected_or_unknown_split' if flag == 'protected' else 'Unknown input fields'):
                    shadow.prepare(source, root/'audit')
                predict.assert_not_called()

    def test_answers_are_bound_to_identity_evidence_and_actual_human_confirmation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            bundle = root/'audit'
            shadow.prepare(fixture(root), bundle)
            response = response_for(bundle)
            variants = []
            bad = deepcopy(response); bad['package_id'] = 'wrong'; variants.append(bad)
            bad = deepcopy(response); bad['attestation']['human_only'] = 1; variants.append(bad)
            bad = deepcopy(response); bad['tasks'][0]['attributes'][0]['evidence']['text'] = 'not in text'; variants.append(bad)
            bad = deepcopy(response); bad['tasks'].append(bad['tasks'][0]); variants.append(bad)
            bad = deepcopy(response); bad['tasks'].pop(); variants.append(bad)
            bad = deepcopy(response); bad['tasks'][0]['attributes'][0]['unit'] = 'TB'; variants.append(bad)
            for i, bad in enumerate(variants):
                path = root/f'bad-{i}.json'; dump(path, bad)
                with self.assertRaises(ValueError):
                    shadow.assess(bundle, path, root/f'result-{i}')
            answers = root/'good.json'; dump(answers, response)
            report = shadow.assess(bundle, answers, root/'result')
            self.assertEqual(report['counts']['correct'], 2)
            self.assertTrue(report['review_complete'])
            self.assertFalse(report['numerical_target_met'])
            self.assertFalse(report['runtime_auto_accept'])
            self.assertFalse(report['independent_reference'])

    def test_pending_or_uncertain_cases_cannot_disappear_from_risk_denominator(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            bundle = root/'audit'
            shadow.prepare(fixture(root), bundle)
            for status in ['unreviewed', 'ambiguous']:
                response = response_for(bundle)
                a = response['tasks'][0]['attributes'][0]
                a.update(status=status, value=None, unit=None, evidence=None, notes='synthetic uncertainty')
                path = root/f'{status}.json'; dump(path, response)
                report = shadow.assess(bundle, path, root/f'result-{status}')
                self.assertEqual(report['sample_size'], 2)
                if status == 'unreviewed':
                    self.assertFalse(report['review_complete'])
                    self.assertIsNone(report['conservative_one_sided_lower_95'])
                else:
                    self.assertEqual(report['human_precision_family_sample'], .5)
                    self.assertEqual(report['counts']['unresolved'], 1)

    def test_html_reuses_existing_form_keeps_untrusted_text_inert_and_no_false_independence(self):
        html = shadow.review_html({'tasks': [{'title': '</script><script>alert(1)</script>'}]})
        self.assertIn('\\u003c/script>', html)
        self.assertNotIn('>Для этих карточек не использовал', html)
        self.assertIn('candidate_checked', html)
        self.assertIn('t.proposal.value', html)
        self.assertNotIn('__PAYLOAD__', html)

    def test_hash_tamper_is_rejected_before_human_assessment(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            bundle = root/'audit'
            shadow.prepare(fixture(root), bundle)
            answer = root/'answers.json'; dump(answer, response_for(bundle))
            with (bundle/'selection.private.jsonl').open('a') as stream:
                stream.write('{}\n')
            with self.assertRaisesRegex(ValueError, 'hash_mismatch'):
                shadow.assess(bundle, answer, root/'result')


if __name__ == '__main__':
    unittest.main()
