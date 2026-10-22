"""Artifact safety, real predictor behavior and advisory-only learned score."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from goodsai.config import load_config, validate_config
from goodsai.confidence import main as make_profile
from goodsai.contracts import Product
from goodsai.learned_confidence import (FORMAT, FEATURE_VERSION, explain, metadata,
                                       predict_score, profile_fingerprint, validate_model)
from goodsai.verify import Extractor
from scripts.research.learn_confidence import experiment, paired_brier_uncertainty, ranking, verified_directory


def model(config=None):
    config=config or load_config()
    return {'format':FORMAT,'feature_version':FEATURE_VERSION,'reference_kind':'catalog_silver',
        'profile_sha256':profile_fingerprint(config),
        'weights':{'intercept':0.,'score':1.,'explicit_role':1.,'cross_field_agreement':1.},
        'platt':{'intercept':0.,'logit':1.},
        'supported_scopes':['761:brand:brand.explicit-title.v1','761:storage_gb:memory.title-pair.v1'],
        'provenance':{'prepared_manifest_sha256':'a'*64,'fit_report_sha256':'b'*64,'independent_reference':False}}


def profile():
    config=load_config();config['runtime']['confidence']={'version':'learned-v1','model':model(config)}
    return config


class LearnedConfidenceTests(unittest.TestCase):
    def test_candidate_variation_facts_and_storage_acceptance_scope_unchanged(self):
        config=profile();config['runtime'].update(auto_accept_enabled=True,auto_accept={'policy_version':'storage-pilot-97-v1','target_precision':.97})
        scores=[]
        base=deepcopy(config);base['runtime'].pop('confidence')
        for description in ('','ROM: 256 GB'):
            p=Product('s','761','Smartphone Samsung Orbit X82 8/256GB black',description)
            before=Extractor(base).predict(p);after=Extractor(config).predict(p)
            for a,b in zip(after['attributes'],before['attributes']):
                if a['attribute']=='storage_gb':scores.append(a['confidence']);self.assertEqual(a['decision'],'auto_accept')
                a['confidence']=b['confidence']
            self.assertEqual(after,before)
        self.assertNotEqual(*scores)

    def test_unknown_scope_falls_back_without_inventing_probability(self):
        p=Product('s','482','Bosch KX-82 2200 Вт')
        self.assertEqual(Extractor(profile()).predict(p),Extractor(load_config()).predict(p))
        m=model();self.assertEqual(predict_score({'score':.8},'unknown',m),.8)
        self.assertEqual(explain({'score':.8},'unknown',m)['status'],'fallback_unsupported_scope')

    def test_profile_or_feature_grammar_change_rejects_artifact(self):
        c=profile();c['rule_scores']['brand']=.84
        with self.assertRaisesRegex(ValueError,'profile'):validate_config(c)
        c=profile()
        with patch('goodsai.learned_confidence.profile_fingerprint',return_value='0'*64),self.assertRaises(ValueError):validate_config(c)

    def test_bad_schema_weights_scopes_and_provenance_are_rejected(self):
        changes=[('format','pickle'),('feature_version','unknown'),('reference_kind','human_probability'),
                 ('weights',{'score':float('nan')}),('weights',{'score':True}),('weights',{'score':float('inf')}),
                 ('weights',{'score':101}),('weights',{'sku=secret':1}),('platt',{'intercept':0,'logit':-1}),
                 ('supported_scopes',['761:cpu:unknown']),('supported_scopes',[]),
                 ('provenance',{'independent_reference':True})]
        for key,value in changes:
            with self.subTest(key=key,value=value):
                m=model();m[key]=value
                with self.assertRaises(ValueError):validate_model(m,load_config())

    def test_explanation_and_metadata_are_honest_and_do_not_expose_vectors(self):
        m=model();v={'intercept':1.,'score':.8,'explicit_role':1.}
        scope=m['supported_scopes'][0];e=explain(v,scope,m)
        self.assertAlmostEqual(e['pre_calibration_logit'],1.8)
        self.assertEqual(e['score'],predict_score(v,scope,m))
        meta=metadata(profile());self.assertEqual(meta['reference_kind'],'catalog_silver')
        self.assertFalse(meta['human_probability_calibrated']);self.assertFalse(meta['new_auto_accept_thresholds'])
        self.assertNotIn('weights',meta);self.assertNotIn('provenance',meta)

    def test_profile_generator_requires_hash_and_roundtrips_json(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'model.json';source.write_text(json.dumps(model()))
            target=root/'profile.json';argv=['confidence','--model',str(source),'--output',str(target)]
            with patch('sys.argv',argv),self.assertRaises(SystemExit):make_profile()
            self.assertFalse(target.exists())
            argv+=['--model-sha256',hashlib.sha256(source.read_bytes()).hexdigest()]
            with patch('sys.argv',argv):make_profile()
            self.assertEqual(load_config(target)['runtime']['confidence']['version'],'learned-v1')
            with patch('sys.argv',argv),self.assertRaises(SystemExit):make_profile()

    def test_review_budget_is_tie_averaged_and_not_label_or_sku_selected(self):
        ps=[{'correct':True}]*8+[{'correct':False}]*2
        self.assertAlmostEqual(ranking(ps,[.8]*10)['capture'],.1)
        self.assertEqual(ranking(ps,[.9]*8+[.1]*2)['capture'],.5)
        self.assertIsNone(ranking([{'correct':True}],[.8])['capture'])

    def test_uncertainty_resamples_families_and_is_reproducible(self):
        ps=[{'group':str(i),'fixed':.8,'correct':True} for i in range(25)]
        a=paired_brier_uncertainty(ps,[.9]*25,repeats=100)
        self.assertEqual(a,paired_brier_uncertainty(ps,[.9]*25,repeats=100))
        self.assertLess(a['interval']['upper'],0)
        self.assertEqual(paired_brier_uncertainty(ps[:3],[.9]*3)['status'],'insufficient_groups')

    def test_prepared_manifest_tamper_and_path_escape_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);(p/'artifact').write_text('safe');sha=hashlib.sha256((p/'artifact').read_bytes()).hexdigest()
            manifest={'status':'complete','files_sha256':{'artifact':sha}}
            (p/'manifest.json').write_text(json.dumps(manifest));verified_directory(p)
            (p/'artifact').write_text('changed')
            with self.assertRaises(ValueError):verified_directory(p)
            manifest['files_sha256']={'../secret':'0'*64};(p/'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):verified_directory(p)

    def test_insufficient_or_leaking_groups_cannot_fit(self):
        ps=[{'group':'same','role':r,'correct':True} for r in ('fit','calibration','diagnostic')]
        with self.assertRaisesRegex(ValueError,'leakage'):experiment(ps)
        for p in ps:p['group']=p['role']
        with self.assertRaisesRegex(ValueError,'support'):experiment(ps)


class LearnedApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_learned_cli_api_and_health(self):
        try:
            from httpx import ASGITransport,AsyncClient
            from goodsai.api import create_app
        except ImportError:self.skipTest('serve/test extras required')
        from goodsai.cli import predict
        from goodsai.data import read_predictions
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);cp=root/'profile.json';cp.write_text(json.dumps(profile()))
            card={'schema_version':'0.1','sku_id':'s','category_id':'761','title':'Smartphone Samsung Orbit X82 8/256GB'}
            ip=root/'input.jsonl';ip.write_text(json.dumps(card)+'\n');out=root/'out.jsonl';predict(ip,out,profile());expected=list(read_predictions(out))[0]
            async with AsyncClient(transport=ASGITransport(app=create_app(str(cp))),base_url='http://test') as client:
                r=await client.post('/predict',json=card);self.assertEqual(r.status_code,200)
                actual=r.json();actual['run_id']=expected['run_id'];self.assertEqual(actual,expected)
                health=(await client.get('/health')).json();self.assertEqual(health['confidence']['version'],'learned-v1')
                self.assertFalse(health['confidence']['human_probability_calibrated'])
