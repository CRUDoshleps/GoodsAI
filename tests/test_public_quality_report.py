"""Aggregate publication guards, using invented metric snapshots only."""
from copy import deepcopy
from argparse import Namespace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.research import export_quality_report as export_tool
from scripts.research.export_quality_report import project, markdown
from goodsai.data import digest


def fixture():
    code, config, input_sha = 'c' * 64, 'd' * 64, 'e' * 64
    metric = {'tp': 1, 'fp': 0, 'fn': 0, 'requested': 1, 'predicted': 1,
              'precision': 1.0, 'recall': 1.0, 'f1': 1.0, 'unassessed_candidates': 0}
    variant = {'reference_kind': 'catalog_silver', 'evaluation_role': 'development_feedback',
        'agreement': metric, 'per_attribute': {'model': metric}, 'per_category': {'482': metric},
        'slices': {'category_attribute': {'482:model': metric}, 'text': {'title_only': metric},
                   'reference_frequency': {'rare': metric}, 'role': {'fit': metric}},
        'grouped_ci': {'status': 'unavailable'},
        'seller_slices': {'known_sellers': 1, 'groups_under_20_requested_pairs': 1, 'macro_f1': None},
        'raw_title': 'SECRET_CARD', 'seller_identifiers': ['SECRET_SELLER']}
    producer = {'git_commit': 'b' * 40, 'code_sha256': code, 'config_sha256': config,
                'input_sha256': input_sha, 'output_sha256': '0' * 64, 'git_dirty': False, 'llm_calls': 0,
                'api_key': 'SECRET_TOKEN'}
    silver = {'freeze': {'reference_kind': 'catalog_silver', 'external_calls': 'forbidden',
                        'before': 'a' * 40, 'after': 'b' * 40, 'input_sha256': input_sha,
                        'reference_sha256': '1' * 64, 'source_bundle_sha256': '2' * 64},
        'variants': {'before': deepcopy(variant), 'after': deepcopy(variant)},
        'paired': {'counts': {k: 0 for k in ('new_tp', 'new_fp', 'lost_tp', 'removed_fp', 'new_fn', 'removed_fn')}},
        'paired_grouped_ci': {'status': 'unavailable'}, 'private_pairs': ['SECRET_PAIR']}
    manual = {'metrics': {'attribute:model': metric, 'category:482': metric}, 'pending_cards': 0,
              'missing_prediction_cards': 0, 'unprocessed_prediction_cards': 0, 'excluded_pairs': 4}
    human = {'sample_kind': 'error_selected_development', 'reference_origin': 'ai_assisted_human_reviewed',
        'independent_reference': False, 'reviewed_attributes': ['model'], 'cards': 1,
        'source_reference_sha256': '3' * 64, 'evaluator_sha256': '4' * 64,
        'method_provenance': {'fixed': {k: producer[k] for k in
            ('git_commit', 'code_sha256', 'config_sha256', 'input_sha256', 'output_sha256')}},
        'metrics': {k: deepcopy(manual) for k in ('historical','reported_candidate','pre_fix_main','fixed')},
        'raw_labels': ['SECRET_LABEL']}
    refs = [{'sku_id': 'SECRET_SKU', 'family_id': 'SECRET_FAMILY', 'category_id': '482',
             'original_split': 'development', 'independent_reference': False, 'ai_assisted': True,
             'annotation_status': 'reviewed', 'title': 'SECRET_CARD', 'annotation_notes': 'SECRET_LABEL'}]
    current = {'code_sha256': code, 'config_sha256': config}
    return silver, human, producer, refs, current


class PublicQualityReportTests(unittest.TestCase):
    def test_only_aggregate_numbers_and_fixed_dimensions_are_published(self):
        report = project(*fixture())
        serialized = json.dumps(report) + markdown(report)
        self.assertNotIn('SECRET_', serialized)
        self.assertIsNone(report['independent_human_quality'])
        self.assertFalse(report['reviewed_regressions']['independent_reference'])
        self.assertEqual(report['catalog_silver']['variants']['after']['reference_frequency']['rare']['tp'], 1)
        self.assertEqual(report['reviewed_regressions']['variants']['fixed']['excluded_other_pairs'], 4)
        self.assertEqual(report['reviewed_regressions']['category_support'], {'482': 1})
        self.assertEqual(report['catalog_silver']['unassessed_model_candidate_delta'], 0)

    def test_wrong_runtime_producer_or_human_role_cannot_be_published_as_current(self):
        for mode in ('code', 'config', 'producer', 'independent', 'test', 'pending', 'input'):
            with self.subTest(mode=mode):
                silver, human, producer, refs, current = fixture()
                if mode in ('code','config'):
                    current[mode + '_sha256'] = 'wrong'
                elif mode == 'producer':
                    producer['code_sha256'] = 'different'
                elif mode == 'independent':
                    human['independent_reference'] = True
                elif mode == 'test':
                    refs[0]['original_split'] = 'test_reserved'
                elif mode == 'pending':
                    human['metrics']['fixed']['pending_cards'] = 1
                else:
                    silver['freeze']['input_sha256'] = 'different'
                with self.assertRaises(ValueError):
                    project(silver, human, producer, refs, current)

    def test_raw_slice_identity_invalid_counts_or_nonfinite_numbers_fail(self):
        for mode in ('slice_identity','count','nan','excluded','hash'):
            with self.subTest(mode=mode):
                silver, human, producer, refs, current = fixture()
                if mode == 'slice_identity':
                    silver['variants']['after']['slices']['text']['SECRET_SKU'] = {'tp': 1, 'fp': 0, 'fn': 0}
                elif mode == 'count':
                    silver['variants']['after']['agreement']['tp'] = True
                elif mode == 'nan':
                    silver['variants']['after']['agreement']['f1'] = float('nan')
                elif mode == 'excluded':
                    human['metrics']['fixed']['excluded_pairs'] = 'SECRET_LABEL'
                else:
                    human['evaluator_sha256'] = 'SECRET_TOKEN'
                with self.assertRaises(ValueError):
                    project(silver, human, producer, refs, current)

    def test_unassessed_delta_and_small_seller_support_are_not_hidden(self):
        args = fixture()
        args[0]['variants']['after']['per_attribute']['model']['unassessed_candidates'] = 1
        report = project(*args)
        self.assertEqual(report['catalog_silver']['unassessed_model_candidate_delta'], 1)
        self.assertEqual(report['catalog_silver']['variants']['after']['seller_summary']['groups_under_20_requested_pairs'], 1)
        self.assertIsNone(report['catalog_silver']['traffic_quality'])

    def test_export_repeats_bytes_and_rejects_changed_reports_or_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            silver, human, producer, refs, current = fixture()
            reference = root / 'reference.jsonl'
            reference.write_text(''.join(json.dumps(r) + '\n' for r in refs), encoding='utf-8')
            human['source_reference_sha256'] = digest(reference)
            paths = {}
            for name, value in (('silver',silver), ('human',human), ('producer',producer)):
                paths[name] = root / (name + '.json')
                paths[name].write_text(json.dumps(value), encoding='utf-8')
            args = Namespace(**paths, reference=reference, silver_sha256=digest(paths['silver']),
                             human_sha256=digest(paths['human']), output_dir=root / 'outputs/one')
            with patch.object(export_tool, 'ROOT', root), patch.object(export_tool, 'identity', return_value=current):
                export_tool.export(args)
                args.output_dir = root / 'outputs/two'
                export_tool.export(args)
                for name in ('quality_20261021.json','quality_20261021.md'):
                    self.assertEqual((root / 'outputs/one' / name).read_bytes(), (root / 'outputs/two' / name).read_bytes())
                    self.assertNotIn(b'\r', (root / 'outputs/one' / name).read_bytes())
                args.output_dir = root / 'outputs/rejected'
                expected = args.silver_sha256
                args.silver_sha256 = 'wrong'
                with self.assertRaisesRegex(ValueError, 'source_report_hash_mismatch'):
                    export_tool.export(args)
                args.silver_sha256 = expected
                reference.write_text('changed',encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'reviewed_reference_hash_mismatch'):
                    export_tool.export(args)
                self.assertFalse(args.output_dir.exists())


if __name__ == '__main__':
    unittest.main()
