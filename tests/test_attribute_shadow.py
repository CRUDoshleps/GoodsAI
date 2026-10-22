"""CONF-006: invented fixtures only; no real annotations, reserve, VM or models."""
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from goodsai.attribute_shadow import Selector, default_plan, fingerprint, validate_plan
from goodsai.config import load_config
from goodsai.contracts import Product
from goodsai.data import digest
from goodsai.silver_prepare import VERSION, assemble
from goodsai.storage_acceptance import candidate_eligible
from goodsai.verify import Extractor
from scripts.research import attribute_shadow as shadow
from scripts.research.audit_splits import dump, write_rows
from scripts.research.human_gold import checked


def products():
    return [Product('p1', '761', 'Смартфон Samsung Orbit X73 8/256GB белый',
                    'Экран 6,4 дюйма. Аккумулятор 4600 мАч.'),
            Product('k1', '482', 'Чайник Bosch KX-82 1,7 л 2200 Вт черный')]


def fixture(root, *, exposed=False):
    config = load_config()
    rows = [p.as_dict() for p in products()]
    # Two phones in the same family exercise selection without double counting.
    rows.append(rows[0] | {'sku_id': 'p2'})
    members = {r['sku_id']: {'family_id': 'phone-family' if r['category_id'] == '761' else 'kettle-family',
                            'split': 'development', 'quarantine_reasons': []} for r in rows}
    catalog = {r['sku_id']: {'category_id': r['category_id'], 'params': []} for r in rows}
    catalog['p1']['params'] = [{'@name': 'Встроенная память (ROM)_search', '#text': '256', '@unit': 'GB'}]
    catalog['p2']['params'] = [{'@name': 'Встроенная память (ROM)_search', '#text': '128', '@unit': 'GB'}]
    inputs, refs, metadata, _ = assemble(rows, catalog, members, config)
    if exposed:
        next(m for m in metadata if m['sku_id'] == 'p1')['exposed'] = True
    bundle = root / 'source'
    bundle.mkdir()
    for name, values in [('input.jsonl', inputs), ('reference.jsonl', refs), ('metadata.jsonl', metadata)]:
        write_rows(bundle / name, values)
    for name in ['train.jsonl', 'support_review.blank.jsonl', 'llm_screening.input.jsonl']:
        write_rows(bundle / name, [])
    dump(bundle / 'train.split.json', {})
    dump(bundle / 'policy.json', {'config': config})
    reseal(bundle)
    plan = root / 'plan.json'
    dump(plan, default_plan(config))
    return bundle, plan


def reseal(bundle):
    manifest = bundle / 'manifest.json'
    if manifest.exists():
        manifest.unlink()
    dump(manifest, {'version': VERSION, 'reference_kind': 'catalog_silver', 'protected_text_exported': False,
                    'artifacts': {p.name: digest(p) for p in bundle.iterdir()}})


def response_for(folder):
    payload = shadow.read(folder / 'tasks.private.json')
    response = {k: payload[k] for k in ['package_id', 'slot', 'reviewer_id']}
    response['attestation'] = {'human_only': True, 'candidate_checked': True, 'exposure_disclosed': True}
    response['tasks'] = [{'task_id': t['task_id'], 'attributes': [
        {'attribute': t['attributes'][0]['attribute'], 'status': 'present', 'notes': '', **deepcopy(t['proposal'])}]}
        for t in payload['tasks']]
    return response


class PlanAndSelectionTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()
        self.plan = default_plan(self.config)
        self.selector = Selector(self.config, self.plan)
        self.extractor = Extractor(self.config)

    def test_all_nine_attributes_twelve_cells_and_individual_targets(self):
        self.assertEqual(len(self.plan['policies']), 12)
        self.assertEqual(len({p['attribute'] for p in self.plan['policies']}), 9)
        self.plan['policies'][0]['target_precision'] = .97
        self.plan['policies'][1]['target_precision'] = .999
        self.assertEqual(validate_plan(self.plan, self.config)['policies'][0]['target_precision'], .97)
        for product in products():
            prediction = self.extractor.predict(product)
            before = deepcopy(prediction)
            selected = self.selector.select(product, prediction)
            self.assertEqual(len(selected), len(self.config['categories'][product.category_id]))
            self.assertTrue(all(reason is None for reason in selected.values()), selected)
            self.assertEqual(prediction, before)
            self.assertTrue(all(a['decision'] == 'review' for a in prediction['attributes']))

    def test_strict_plan_schema_units_scores_missing_cells_and_hash(self):
        cases = []
        for field, value in [('target_precision', True), ('target_precision', float('nan')),
                             ('target_precision', 0), ('target_precision', 1.01),
                             ('min_rule_score', -1), ('audit_families', True), ('unit', 'MB'),
                             ('rule_ids', ['invented.rule']), ('rule_ids', ['memory.context.v1'] * 2)]:
            p = deepcopy(self.plan)
            p['policies'][0][field] = value
            cases.append(p)
        cases.extend([self.plan | {'typo': True}, self.plan | {'policies': self.plan['policies'][:-1]},
                      self.plan | {'config_sha256': '0'*64}, self.plan | {'policies': self.plan['policies'] * 2},
                      self.plan | {'confidence_level': 1}])
        for plan in cases:
            with self.subTest(plan=repr(plan)[:100]), self.assertRaises(ValueError):
                validate_plan(plan, self.config)

    def test_memory_conflicts_negation_accessory_and_absent_values_not_selected(self):
        p = Product('conflict', '761', 'Смартфон Samsung Orbit X73 8/256GB', 'Встроенная память 128 ГБ.')
        selected = self.selector.select(p, self.extractor.predict(p))
        self.assertIsNotNone(selected['761:storage_gb'])
        self.assertEqual(selected['761:ram_gb'], 'memory_conflict')
        for p in [Product('x', '761', 'Чехол для смартфона Samsung Orbit X73 8/256GB белый'),
                  Product('x', '482', 'Мощность 2200 Вт'),
                  Product('x', '482', 'Чайник Bosch KX-82', 'Без мощности 2200 Вт; нет объёма 1,7 л.')]:
            selected = self.selector.select(p, self.extractor.predict(p))
            for key in [k for k in selected if k.endswith(('power_w', 'capacity_l'))]:
                self.assertIsNotNone(selected[key])

    def test_forged_rule_id_score_and_llm_method_do_not_inherit_rule_authority(self):
        p = products()[0]
        original = self.extractor.predict(p)
        for field, value in [('rule_id', 'model.labelled.v2'), ('confidence', .99), ('method', 'llm')]:
            row = deepcopy(original)
            a = next(a for a in row['attributes'] if a['attribute'] == 'model')
            a[field] = value
            self.assertIsNotNone(self.selector.select(p, row)['761:model'])

    def test_every_field_rechecks_actual_rule_provenance_and_protected_flags(self):
        for p in products():
            original = self.extractor.predict(p)
            for index, attr in enumerate(original['attributes']):
                row = deepcopy(original)
                row['attributes'][index]['confidence'] = .123
                with self.subTest(category=p.category_id, attr=attr['attribute']):
                    self.assertEqual(self.selector.select(p, row)[p.category_id + ':' + attr['attribute']],
                                     'rule_provenance_not_reproducible')
            protected = Product(p.sku_id, p.category_id, p.title, p.description, ('TRAIN',))
            self.assertTrue(all(r == 'protected_input' for r in self.selector.select(protected, original).values()))

    def test_storage_selection_matches_existing_scope_and_raw_score_is_only_filter(self):
        p = products()[0]
        row = self.extractor.predict(p)
        self.assertEqual(self.selector.select(p, row)['761:storage_gb'] is None, candidate_eligible(row, p))
        changed = deepcopy(self.plan)
        next(p for p in changed['policies'] if p['attribute'] == 'storage_gb')['min_rule_score'] = 1
        self.assertEqual(Selector(self.config, changed).select(p, row)['761:storage_gb'], 'below_raw_score_filter')
        from scripts.research.storage_pilot import pilot_config
        with self.assertRaisesRegex(ValueError, 'disabled'):
            Selector(pilot_config(), default_plan(pilot_config()))


class PackageTests(unittest.TestCase):
    def test_protocol_and_reused_helpers_survive_submission_filter(self):
        from scripts.release.publish_gitea import allowed
        for path in [shadow.PROTOCOL, Path(shadow.__file__), shadow.TEMPLATE,
                     shadow.ROOT / 'src/goodsai/attribute_shadow.py',
                     shadow.ROOT / 'scripts/research/storage_shadow.py']:
            self.assertTrue(path.is_file())
            self.assertTrue(allowed(path.relative_to(shadow.ROOT).as_posix()), str(path))

    def prepare(self, root, **kwargs):
        source, plan = fixture(root, **kwargs)
        report = shadow.prepare(source, plan, root / 'audit', reviewer='synthetic-not-human')
        return source, plan, report

    def test_full_prepare_reports_all_fields_without_fabricating_human_results(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, plan, report = self.prepare(root)
            self.assertEqual(len(report['fields']), 12)
            self.assertEqual(report['audit_tasks'], 12)
            self.assertEqual(report['fields']['761:storage_gb']['catalog'], {'tp': 1, 'mismatch': 1, 'unknown': 0, 'conflict': 0})
            self.assertEqual(report['fields']['482:capacity_l']['catalog']['unknown'], 1)
            self.assertTrue(all(v['human_precision'] is None and not v['runtime_authorized'] for v in report['fields'].values()))
            self.assertTrue(report['repeat_predictions_identical'])
            audit = root / 'audit'
            checked(audit, 'attribute-shadow')
            blank = shadow.read(audit / 'answers.blank.json')
            self.assertTrue(all(t['attributes'][0]['status'] == 'unreviewed' for t in blank['tasks']))
            html = (audit / 'review.html').read_text()
            self.assertIn('candidate_checked', html)
            self.assertIn('unreviewed', html)
            self.assertNotIn('params', html)
            if os.name != 'nt':
                self.assertEqual(audit.stat().st_mode & 0o777, 0o700)
                self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in audit.iterdir()))
            first = (audit / 'selection.private.jsonl').read_bytes()
            repeat = shadow.prepare(source, plan, root / 'again', reviewer='synthetic-not-human')
            self.assertEqual(first, (root / 'again' / 'selection.private.jsonl').read_bytes())
            self.assertEqual(report['fields'], repeat['fields'])
            with self.assertRaises(ValueError):
                shadow.prepare(source, plan, audit, reviewer='synthetic-not-human')

    def test_family_exposure_propagates_to_duplicate_skus_and_receipts(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, plan, _ = self.prepare(root)
            seen = root / 'seen.jsonl'
            write_rows(seen, [{'sku_id': 'p2'}])
            report = shadow.prepare(source, plan, root / 'exposed-audit', seen_paths=[seen], reviewer='synthetic')
            self.assertEqual(report['fields']['761:ram_gb']['audit_sample_size'], 0)
            self.assertEqual(report['fields']['482:brand']['audit_sample_size'], 1)
            other = root / 'prior-family.jsonl'
            write_rows(other, [{'sku_id': 'outside-current-bundle', 'family_id': 'phone-family'}])
            cross_bundle = shadow.prepare(source, plan, root / 'cross-bundle-audit', seen_paths=[other], reviewer='synthetic')
            self.assertEqual(cross_bundle['fields']['761:ram_gb']['audit_sample_size'], 0)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            _, _, report = self.prepare(root, exposed=True)
            self.assertEqual(report['fields']['761:ram_gb']['audit_sample_size'], 0)

    def test_protected_split_flag_targets_and_cross_role_family_fail_before_publication(self):
        for case in ['split', 'flag', 'target', 'role']:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                source, plan = fixture(root)
                if case in {'split', 'role'}:
                    path = source / 'metadata.jsonl'
                    rows = [json.loads(s) for s in path.read_text().splitlines()]
                    next(m for m in rows if m['sku_id'] == 'p1')['original_split' if case == 'split' else 'role'] = 'test_reserved' if case == 'split' else 'different-valid-role'
                    if case == 'role':
                        first = next(m for m in rows if m['sku_id'] == 'p1')
                        other = next(m for m in rows if m['sku_id'] == 'p2')
                        first['role'] = 'fit' if other['role'] != 'fit' else 'calibration'
                else:
                    path = source / 'input.jsonl'
                    rows = [json.loads(s) for s in path.read_text().splitlines()]
                    rows[0]['source_flags' if case == 'flag' else 'vendor'] = ['closed_test'] if case == 'flag' else 'secret'
                path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
                reseal(source)
                with self.assertRaises(ValueError):
                    shadow.prepare(source, plan, root / 'audit', reviewer='synthetic')
                self.assertFalse((root / 'audit').exists())

    def test_source_mutation_and_bad_reference_do_not_publish_partial_package(self):
        for case in ['changed', 'bad_reference']:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                source, plan = fixture(root)
                original = shadow.predict
                if case == 'bad_reference':
                    path = source / 'reference.jsonl'
                    rows = [json.loads(s) for s in path.read_text().splitlines()]
                    rows[0]['attributes'] = []
                    path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
                    reseal(source)
                def mutate(*args, **kwargs):
                    result = original(*args, **kwargs)
                    if case == 'changed':
                        with (source / 'policy.json').open('a') as stream:
                            stream.write(' ')
                    return result
                with patch.object(shadow, 'predict', side_effect=mutate), self.assertRaises(ValueError):
                    shadow.prepare(source, plan, root / 'audit', reviewer='synthetic')
                self.assertFalse((root / 'audit').exists())

    def test_assess_keeps_bounds_and_targets_separate_for_every_field(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, plan = fixture(root)
            p = shadow.read(plan)
            p['policies'][0]['target_precision'] = .01  # Deliberately easy synthetic numerical target, never runtime.
            plan.write_text(json.dumps(p))
            shadow.prepare(source, plan, root / 'audit', reviewer='synthetic-not-human')
            response = response_for(root / 'audit')
            path = root / 'answers.json'
            dump(path, response)
            report = shadow.assess(root / 'audit', path, root / 'reviewed')
            self.assertEqual(report['fields']['761:brand']['one_sided_lower_95'], .05)
            self.assertTrue(report['fields']['761:brand']['numerical_target_met'])
            self.assertFalse(report['fields']['761:brand']['simultaneous_target_met'])
            self.assertFalse(report['fields']['761:ram_gb']['numerical_target_met'])
            self.assertTrue(all(not f['runtime_authorized'] for f in report['fields'].values()))
            self.assertFalse(report['runtime_auto_accept_changed'])
            self.assertFalse(report['independent_reference'])
            checked(root / 'reviewed', 'attribute-shadow-reviewed')
            next_run = shadow.prepare(source, plan, root / 'next',
                                     seen_paths=[root / 'reviewed' / 'exposure.receipt.jsonl'], reviewer='synthetic')
            self.assertEqual(next_run['audit_tasks'], 0)

    def test_pending_uncertain_and_wrong_labels_are_not_success(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.prepare(root)
            response = response_for(root / 'audit')
            response['tasks'][0]['attributes'][0].update(status='unreviewed', value=None, unit=None, evidence=None)
            response['tasks'][1]['attributes'][0].update(status='ambiguous', value=None, unit=None, evidence=None, notes='uncertain')
            response['tasks'][2]['attributes'][0].update(status='absent', value=None, unit=None, evidence=None)
            path = root / 'answers.json'
            dump(path, response)
            report = shadow.assess(root / 'audit', path, root / 'reviewed')
            self.assertEqual(report['fields']['761:brand']['status'], 'pending')
            self.assertIsNone(report['fields']['761:brand']['one_sided_lower_95'])
            self.assertEqual(report['fields']['761:model']['counts']['unresolved'], 1)
            self.assertEqual(report['fields']['761:model']['one_sided_lower_95'], 0)
            self.assertEqual(report['fields']['761:storage_gb']['counts']['incorrect'], 1)

    def test_invalid_attestation_partial_answers_evidence_hash_and_frozen_plan_rejected(self):
        for case in ['attestation', 'partial', 'evidence', 'tamper', 'plan']:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                _, plan, _ = self.prepare(root)
                response = response_for(root / 'audit')
                if case == 'attestation':
                    response['attestation']['human_only'] = 1
                elif case == 'partial':
                    response['tasks'].pop()
                elif case == 'evidence':
                    response['tasks'][0]['attributes'][0]['evidence']['start'] += 1
                elif case == 'tamper':
                    with (root / 'audit' / 'diagnostics.json').open('a') as stream:
                        stream.write(' ')
                else:
                    with plan.open('a') as stream:
                        stream.write(' ')
                answers = root / 'answers.json'
                dump(answers, response)
                with self.assertRaises(ValueError):
                    shadow.assess(root / 'audit', answers, root / 'reviewed')
                self.assertFalse((root / 'reviewed').exists())

    def test_cli_has_safe_failure_and_plan_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(shadow.main(['plan', '--output', str(root / 'plan.json')]), 0)
            saved = (root / 'plan.json').read_bytes()
            with redirect_stderr(io.StringIO()) as error:
                self.assertEqual(shadow.main(['plan', '--output', str(root / 'plan.json')]), 2)
            self.assertEqual(saved, (root / 'plan.json').read_bytes())
            self.assertNotIn(str(root), error.getvalue())
