"""Hybrid boundaries; no download or optional ML imports in these tests."""
from copy import deepcopy
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from goodsai.contracts import Product, load_config, validate_prediction
from goodsai.experimental_gliner import CHECKPOINT, ENCODER, HybridExtractor, brand_candidates, file_hash, validate_artifact
from goodsai.span_index import visible_view
from goodsai.verify import Extractor


class Backend:
    def __init__(self, entities=None, failure=None):
        self.entities = entities or []
        self.failure = failure
        self.calls = 0

    def predict(self, text):
        self.calls += 1
        if self.failure:
            raise self.failure
        return self.entities


def entity(text, value='Zorion', occurrence=0, **kwargs):
    start = -1
    for _ in range(occurrence + 1):
        start = text.index(value, start+1)
    return dict({'label':'brand', 'start':start, 'end':start+len(value), 'text':value, 'score':0.9}, **kwargs)


class HybridTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()

    def test_known_brand_and_unsupported_category_never_call_model(self):
        backend = Backend(failure=AssertionError('must not be called'))
        hybrid = HybridExtractor(self.config, backend)
        for p in [Product('x','761','Смартфон Samsung QA-901'), Product('x','unknown','Zorion')]:
            self.assertEqual(hybrid.predict(p,'same'), Extractor(self.config).predict(p,'same'))
        self.assertEqual(backend.calls,0)

    def test_recovers_brand_and_preserves_every_other_rule_decision(self):
        p = Product('x','761','Смартфон Zorion QX-900 8/256GB')
        b = Extractor(self.config).predict(p,'same')
        h = HybridExtractor(self.config,Backend([entity(p.title)])).predict(p,'same')
        self.assertEqual(h['attributes'][1:], b['attributes'][1:])
        a = h['attributes'][0]
        self.assertEqual((a['value'],a['method'],a['decision'],a['confidence_kind']),
                         ('Zorion','model','review','heuristic'))
        validate_prediction(h,self.config,p)

    def test_excludes_multiword_brand_and_never_fills_model(self):
        p = Product('x','761','Смартфон Zorion Deluxe QX-900')
        entities = [entity(p.title,'Zorion Deluxe'),entity(p.title,'QX-900',label='product model')]
        h = HybridExtractor(self.config,Backend(entities)).predict(p)
        self.assertIsNone(h['attributes'][0]['value'])
        self.assertIn('model_no_safe_candidate',h['attributes'][0]['reason_codes'])
        self.assertEqual(h['attributes'][1]['method'],'rule')

    def test_negative_roles_are_rejected(self):
        for prefix in ['Чехол','Аксессуар','Смартфон для','Телефон совместим с','Смартфон не','Смартфон без']:
            with self.subTest(prefix=prefix):
                p = Product('x','761',prefix+' Zorion QX-900')
                h = HybridExtractor(self.config,Backend([entity(p.title)])).predict(p)
                self.assertIsNone(h['attributes'][0]['value'])

    def test_conflicting_entities_abstain_and_duplicates_keep_exact_occurrence(self):
        p = Product('x','761','Смартфон Zorion Vardex Zorion')
        entities = [entity(p.title),entity(p.title,'Vardex')]
        h = HybridExtractor(self.config,Backend(entities)).predict(p)
        self.assertIsNone(h['attributes'][0]['value'])
        self.assertIn('conflicting_model_evidence',h['attributes'][0]['reason_codes'])
        h = HybridExtractor(self.config,Backend([entity(p.title,occurrence=1)])).predict(p)
        self.assertEqual(h['attributes'][0]['evidence']['start'],p.title.rindex('Zorion'))

    def test_unicode_inline_html_and_entities_preserve_raw_offsets(self):
        p = Product('x','761','😀 Смартфон Zor<b>i</b>on QX-900')
        text = visible_view(p.title)[0]
        h = HybridExtractor(self.config,Backend([entity(text)])).predict(p)
        a = h['attributes'][0]
        self.assertEqual(a['value'],'Zorion')
        self.assertEqual(a['evidence']['text'],'Zor<b>i</b>on')
        validate_prediction(h,self.config,p)
        p = Product('x','761','Смартфон Zor&#105;on')
        h = HybridExtractor(self.config,Backend([entity(visible_view(p.title)[0])])).predict(p)
        self.assertEqual(h['attributes'][0]['evidence']['text'],'Zor&#105;on')

    def test_hidden_and_comment_boundaries_cannot_be_crossed(self):
        for title in ['Zor<script>hidden</script>ion','Zor<!-- hidden -->ion','Zor<br>ion']:
            p = Product('x','761',title)
            text = visible_view(title)[0]
            e = {'label':'brand','start':0,'end':len(text),'text':text,'score':.9}
            self.assertEqual(brand_candidates(p,self.config,[e]),[])

    def test_malformed_offsets_scores_and_quotes_cannot_become_candidates(self):
        p = Product('x','761','Смартфон Zorion')
        valid = entity(p.title)
        for delta in [{'start':-1},{'end':9999},{'start':True},{'score':float('nan')},
                      {'score':True},{'score':.49},{'text':'invented'},{'label':'model'}]:
            with self.subTest(delta=delta):
                e = deepcopy(valid); e.update(delta)
                self.assertEqual(brand_candidates(p,self.config,[e]),[])

    def test_model_failure_keeps_rules_and_latches_without_private_error(self):
        p = Product('x','761','Смартфон Zorion 8/256GB')
        backend = Backend(failure=RuntimeError('private input must not leak'))
        h = HybridExtractor(self.config,backend)
        for _ in range(2):
            got = h.predict(p,'same'); baseline = Extractor(self.config).predict(p,'same')
            self.assertEqual(got['attributes'][1:],baseline['attributes'][1:])
            self.assertIn('model_unavailable',got['attributes'][0]['reason_codes'])
            self.assertNotIn('private',str(got))
        self.assertEqual(backend.calls,1)

    def test_long_source_is_bounded_without_model_call(self):
        p = Product('x','761','Zorion '+('x'*65536))
        backend = Backend()
        got = HybridExtractor(self.config,backend).predict(p)
        self.assertEqual(backend.calls,0)
        self.assertIn('model_source_too_long',got['attributes'][0]['reason_codes'])

    def test_missing_or_unpinned_artifact_fails_before_model_loading(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(OSError): validate_artifact(Path(d)/'missing')
            (Path(d)/'artifact.json').write_text('{}')
            with self.assertRaises(ValueError): validate_artifact(d)

    def test_unlisted_tokenizer_or_pickle_assets_rejected_before_loading(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            (root/'gliner').mkdir(); (root/'encoder').mkdir()
            contents = {'gliner/gliner_config.json': json.dumps({'model_name':str(root/'encoder')}),
                        'gliner/model.safetensors':'synthetic weights, never loaded',
                        'encoder/config.json':'{}', 'encoder/tokenizer_config.json':'{}', 'encoder/spm.model':'synthetic tokenizer'}
            for name, text in contents.items(): (root/name).write_text(text, encoding='utf-8')
            hashes = {name:file_hash(root/name) for name in contents}
            (root/'artifact.json').write_text(json.dumps({'checkpoint_revision':CHECKPOINT,
                'encoder_revision':ENCODER, 'sha256':hashes}), encoding='utf-8')
            with patch('goodsai.experimental_gliner.WEIGHTS_SHA256', hashes['gliner/model.safetensors']):
                self.assertEqual(validate_artifact(root),root)
                for name in ['gliner/pytorch_model.bin','encoder/tokenizer.json','encoder/custom.py']:
                    extra = root/name; extra.write_text('unlisted', encoding='utf-8')
                    with self.subTest(name=name), self.assertRaisesRegex(ValueError,'Unlisted'):
                        validate_artifact(root)
                    extra.unlink()


if __name__ == '__main__': unittest.main()
