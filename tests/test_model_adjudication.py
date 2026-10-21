"""Synthetic frozen-error review; no real catalogue cards or independent claims."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.research import prepare_model_adjudication as review
from scripts.research.development_review import record_feedback
from goodsai.data import digest
from goodsai.contracts import Product, load_config
from goodsai.verify import Extractor


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True) + "\n", encoding="utf-8")


def rows(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(x) + "\n" for x in values), encoding="utf-8")


def seal(path, metadata):
    save(path / "manifest.json", metadata | {"artifacts": {
        p.relative_to(path).as_posix(): digest(p) for p in sorted(path.rglob('*'))
        if p.is_file() and p.name != 'manifest.json'}})


def fixture(root, *, protected=False, shared_protected_family=False):
    bundle, comparison = root / 'bundle', root / 'comparison'
    rows(bundle / 'input.jsonl', [{'schema_version': '0.1', 'sku_id': 'invented-kettle',
        'category_id': '482', 'title': 'Электрочайник Bosch Demo Q520W', 'description': None},
        {'sku_id': 'protected', 'title': ['NEVER_PARSE_RESERVED_TEXT']}])
    rows(bundle / 'metadata.jsonl', [
        {'sku_id': 'invented-kettle', 'category_id': '482', 'family_id': 'family-1',
         'original_split': 'test_reserved' if protected else 'validation', 'evaluation_role': 'development_feedback'},
        {'sku_id': 'protected', 'category_id': '482',
         'family_id': 'family-1' if shared_protected_family else 'protected-family', 'original_split': 'test_reserved'}])
    for name in ('policy.json', 'train.split.json'):
        save(bundle / name, {})
    for name in ('reference.jsonl', 'train.jsonl', 'support_review.blank.jsonl', 'llm_screening.input.jsonl'):
        rows(bundle / name, [])
    seal(bundle, {'version': 'catalog-silver-2', 'reference_kind': 'catalog_silver'})
    save(comparison / 'config.json', {})
    freeze = {'bundle_manifest_sha256': digest(bundle / 'manifest.json'), 'reference_kind': 'catalog_silver',
              'external_calls': 'forbidden', 'baseline_sha': 'a' * 40, 'candidate_sha': 'b' * 40,
              'config_file_sha256': digest(comparison / 'config.json')}
    save(comparison / 'freeze.json', freeze)
    rows(comparison / 'changed_pairs.private.jsonl', [
        {'sku_id': 'invented-kettle', 'attribute': 'model', 'new_fp': 0, 'lost_tp': 1}])
    for mode, sha in (('historical', 'a' * 40), ('candidate', 'b' * 40)):
        rows(comparison / mode / 'cold.jsonl', [])
        save(comparison / mode / 'cold.manifest.json', {'git_commit': sha, 'git_dirty': False,
             'llm_calls': 0, 'input_sha256': digest(bundle / 'input.jsonl'),
             'output_sha256': digest(comparison / mode / 'cold.jsonl')})
    save(comparison / 'run_stats.json', {'freeze': freeze, 'evaluation_role': 'development_feedback',
         'paired': {'slices': {'attribute:model': {'new_fp': 0, 'lost_tp': 1}}}})
    seal(comparison, {'schema': 'goodsai-frozen-comparison-output-1'})
    return bundle, comparison


def prepare(root, bundle, comparison):
    # Production restricts to ROOT/outputs; isolate that boundary in a temp workspace.
    with patch.object(review, 'ROOT', root):
        return review.prepare(bundle, comparison, digest(bundle / 'manifest.json'),
                              digest(comparison / 'manifest.json'), root / 'outputs/selected')


class ModelAdjudicationTests(unittest.TestCase):
    def test_complete_selection_is_unreviewed_and_gates_reserved_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a, b = fixture(root)
            self.assertEqual(prepare(root, a, b)['cards'], 1)
            tasks = list(review.read_jsonl(root / 'outputs/selected/development.tasks.jsonl'))
            self.assertEqual(tasks[0]['review_id'], 'M01')
            self.assertEqual(tasks[0]['original_split'], 'validation')
            self.assertEqual(tasks[0]['split'], 'development')
            self.assertEqual(tasks[0]['attributes'][0]['status'], 'unreviewed')
            self.assertFalse(tasks[0]['independent_reference'])
            self.assertNotIn('counts', tasks[0])
            with self.assertRaisesRegex(ValueError, 'new_private_output'):
                prepare(root, a, b)

    def test_selected_reserve_and_shared_reserve_family_fail_before_text(self):
        for flag in ('protected', 'shared_protected_family'):
            with self.subTest(flag=flag), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                a, b = fixture(root, **{flag: True})
                with self.assertRaisesRegex(ValueError, 'protected_or_unknown'):
                    prepare(root, a, b)
                self.assertFalse((root / 'outputs/selected').exists())

    def test_tampered_and_incomplete_frozen_comparisons_are_rejected(self):
        for mode in ('tampered', 'missing_manifest_entry', 'producer_input', 'omitted_change'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                a, b = fixture(root)
                if mode == 'tampered':
                    save(b / 'config.json', {'unexpected': True})
                elif mode == 'missing_manifest_entry':
                    m = review.read(b / 'manifest.json')
                    del m['artifacts']['freeze.json']
                    save(b / 'manifest.json', m)
                elif mode == 'producer_input':
                    p = b / 'candidate/cold.manifest.json'
                    m = review.read(p)
                    m['input_sha256'] = 'wrong'
                    save(p, m)
                    seal(b, {'schema': 'goodsai-frozen-comparison-output-1'})
                else:
                    rows(b / 'changed_pairs.private.jsonl', [])
                    seal(b, {'schema': 'goodsai-frozen-comparison-output-1'})
                with self.assertRaises(ValueError):
                    prepare(root, a, b)

    def test_authored_draft_and_feedback_keep_prediction_exposure_and_origin(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a, b = fixture(root)
            prepare(root, a, b)
            save(root / 'decisions.json', {'M01': {'value': 'Demo Q520W', 'unit': None,
                'field': 'title', 'quote': 'Demo Q520W', 'note': 'Invented explicit model.'}})
            with patch.object(review, 'ROOT', root):
                review.draft(root / 'outputs/selected', root / 'decisions.json', root / 'outputs/draft')
            draft = root / 'outputs/draft'
            self.assertIn('M01–M01', (draft / 'review.md').read_text(encoding='utf-8'))
            self.assertEqual(review.read(draft / 'draft.manifest.json')['human_reviewed_cards'], 0)
            feedback = root / 'feedback.json'
            save(feedback, {'source_draft_sha256': digest(draft / 'development.ai-draft.jsonl'),
                            'reviewer': 'SyntheticHuman', 'confirm_all_existing_labels': False})
            with self.assertRaisesRegex(ValueError, 'explicit_global_confirmation'):
                record_feedback(draft, feedback, root / 'outputs/reviewed')
            f = review.read(feedback)
            f['confirm_all_existing_labels'] = True
            save(feedback, f)
            record_feedback(draft, feedback, root / 'outputs/reviewed')
            r = review.read(root / 'outputs/reviewed/review.manifest.json')
            self.assertTrue(r['predictions_used'])
            self.assertFalse(r['independent_reference'])
            self.assertIsNone(r['f1'])
            row = next(review.read_jsonl(root / 'outputs/reviewed/development.human-reviewed.jsonl'))
            self.assertEqual(row['annotation_origin'], 'ai_assisted_human_reviewed')
            self.assertTrue(row['ai_assisted'])
            self.assertEqual(row['attributes'][0]['evidence']['text'], 'Demo Q520W')

    def test_draft_cannot_invent_model_outside_witness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a, b = fixture(root)
            prepare(root, a, b)
            save(root / 'decisions.json', {'M01': {'value': 'Different Q520W', 'unit': None,
                'field': 'title', 'quote': 'Demo Q520W', 'note': 'Must be rejected.'}})
            with patch.object(review, 'ROOT', root), self.assertRaisesRegex(ValueError, 'Model changes'):
                review.draft(root / 'outputs/selected', root / 'decisions.json', root / 'outputs/draft')

    def test_model_only_review_reuses_evaluator_and_excludes_other_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a, b = fixture(root)
            prepare(root, a, b)
            save(root / 'decisions.json', {'M01': {'value': 'Demo Q520W', 'unit': None,
                'field': 'title', 'quote': 'Demo Q520W', 'note': 'Invented explicit model.'}})
            with patch.object(review, 'ROOT', root):
                review.draft(root / 'outputs/selected', root / 'decisions.json', root / 'outputs/draft')
            save(root / 'feedback.json', {'source_draft_sha256': digest(root / 'outputs/draft/development.ai-draft.jsonl'),
                                         'reviewer': 'SyntheticHuman', 'confirm_all_existing_labels': True})
            reference = root / 'outputs/reviewed'
            record_feedback(root / 'outputs/draft', root / 'feedback.json', reference)
            p = Product.from_dict(next(review.read_jsonl(a / 'input.jsonl')))
            row = Extractor(load_config()).predict(p)
            self.assertEqual(next(x for x in row['attributes'] if x['attribute'] == 'model')['value'], 'Demo Q520W')
            save(root / 'config.json', load_config())
            specs = []
            for mode in ('before', 'after'):
                predicted = json.loads(json.dumps(row))
                if mode == 'before':
                    model = next(x for x in predicted['attributes'] if x['attribute'] == 'model')
                    model.update(value=None, unit=None, confidence=None, decision='abstain',
                                 rule_id=None, evidence=None, reason_codes=['not_found_by_rules'])
                path = root / (mode + '.jsonl')
                rows(path, [predicted])
                save(path.with_suffix('.manifest.json'), {'rows': 1, 'git_dirty': False, 'llm_calls': 0,
                    'input_sha256': 'synthetic-common-input', 'output_sha256': digest(path),
                    'git_commit': ('a' if mode == 'before' else 'b') * 40})
                specs.append(mode + '=' + str(path))
            reference_sha = digest(reference / 'development.human-reviewed.jsonl')
            # Only patch the private destination boundary, not the actual metric implementation/hash.
            with patch.object(review, 'new_output', side_effect=lambda p: Path(p)):
                result = review.evaluate_models(reference, reference_sha, specs, root / 'config.json', root / 'scored')
            self.assertFalse(result['independent_reference'])
            self.assertEqual(result['metrics']['before']['fn'], 1)
            self.assertEqual(result['metrics']['after']['tp'], 1)
            report = review.read(root / 'scored/metrics.json')
            self.assertEqual(report['sample_kind'], 'error_selected_development')
            self.assertEqual(report['metrics']['after']['excluded_pairs'], 4)
            self.assertEqual(set(report['metrics']['after']['metrics']),
                {'micro', 'attribute:model', 'category:482', 'category_attribute:482:model'})
            self.assertEqual(report['paired_model_transitions']['before->after'], {'FN->TP': 1})
            for mode in ('before', 'after'):
                self.assertEqual(digest(root / (mode + '.jsonl')),
                    review.read(root / (mode + '.manifest.json'))['output_sha256'])
            with self.assertRaisesRegex(ValueError, 'reviewed_reference_mismatch'):
                review.evaluate_models(reference, 'wrong', specs, root / 'config.json', root / 'rejected')
            producer = review.read(root / 'after.manifest.json')
            producer['input_sha256'] = 'different-input'
            save(root / 'after.manifest.json', producer)
            with patch.object(review, 'new_output', side_effect=lambda p: Path(p)), \
                    self.assertRaisesRegex(ValueError, 'different_frozen_inputs'):
                review.evaluate_models(reference, reference_sha, specs, root / 'config.json', root / 'different')


if __name__ == '__main__':
    unittest.main()
