"""Synthetic regressions for opt-in scoring and the development experiment."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from goodsai.confidence import contextual_score, row_features
from goodsai.config import load_config, validate_config
from goodsai.contracts import Product
from goodsai.policy import policy_for_settings
from goodsai.verify import Extractor
from scripts.research.compare_confidence import SEED, learned_comparison, partition, run


def profile():
    c = load_config()
    c['runtime']['confidence'] = {'version': 'context-v1'}
    return c


def attributes(row):
    return {a['attribute']: a for a in row['attributes']}


class ConfidenceTests(unittest.TestCase):
    def test_default_is_byte_equivalent_to_explicit_fixed(self):
        c = load_config(); fixed = deepcopy(c); fixed['runtime']['confidence'] = {'version': 'fixed-v1'}
        for title in ('Smartphone Samsung Orbit X82 8/256GB black', 'Bosch KX-82', 'unknown'):
            p = Product('synthetic', '761', title)
            self.assertEqual(Extractor(c).predict(p), Extractor(fixed).predict(p))

    def test_context_changes_per_instance_without_changing_facts_or_decisions(self):
        scores = []
        for description in ('Память 8/256GB', 'Объем встроенной памяти: 256 GB', 'Накопитель: 256 GB'):
            p = Product('synthetic', '761', 'Смартфон Samsung Orbit X82', description)
            old = Extractor(load_config()).predict(p); new = Extractor(profile()).predict(p)
            scores.append(attributes(new)['storage_gb']['confidence'])
            for a,b in zip(old['attributes'],new['attributes']):
                self.assertEqual({k:v for k,v in a.items() if k!='confidence'}, {k:v for k,v in b.items() if k!='confidence'})
        self.assertGreater(len(set(scores)),1)

    def test_hidden_label_does_not_boost_and_identical_text_is_not_corroboration(self):
        extractor = Extractor(profile())
        plain = Product('s','761','Samsung Orbit X82 8/256GB')
        hidden = Product('s','761','<script>Brand:</script>Samsung Orbit X82 8/256GB')
        self.assertEqual(attributes(extractor.predict(plain))['brand']['confidence'],attributes(extractor.predict(hidden))['brand']['confidence'])
        duplicate = Product('s','761',plain.title,plain.title)
        self.assertEqual(attributes(extractor.predict(plain))['brand']['confidence'],attributes(extractor.predict(duplicate))['brand']['confidence'])

    def test_conflicts_and_absence_remain_abstain(self):
        p = Product('s','761','Смартфон Samsung Orbit X82 8/256GB','Встроенная память 128 GB')
        a = attributes(Extractor(profile()).predict(p))
        self.assertEqual(a['storage_gb']['decision'],'abstain'); self.assertIsNone(a['storage_gb']['confidence'])
        self.assertEqual(a['battery_mah']['decision'],'abstain')

    def test_no_sku_or_metadata_features(self):
        p = Product('s','761','Samsung Orbit X82 8/256GB')
        x = Extractor(load_config()); r = x.predict(p); grouped = {}
        for c in x.rules.candidates(p):
            if x.gate_factory.create(p).reason(c) is None: grouped.setdefault(c.attribute,[]).append(c)
        vectors = row_features(p,r,grouped)
        self.assertEqual(vectors,row_features(Product('another','761',p.title),r,grouped))
        self.assertFalse(any('family' in k or 'sku' in k or 'correct' in k for v in vectors.values() for k in v))

    def test_profile_validation_and_policy_provenance(self):
        c = profile()
        self.assertEqual(policy_for_settings(c)['decisions']['confidence'],{'version':'context-v1'})
        for invalid in ({'version':'probability'}, {'version':'context-v1','threshold':.97}, None):
            c['runtime']['confidence']=invalid
            with self.assertRaises(ValueError): validate_config(c)

    def test_storage_pilot_compatible_without_scope_expansion(self):
        c = profile(); c['runtime'].update(auto_accept_enabled=True,auto_accept={'policy_version':'storage-pilot-97-v1','target_precision':.97})
        for title,decision in [('Smartphone Samsung Orbit X82 8/256GB','auto_accept'),('Samsung Orbit X82 8/256GB','review')]:
            a = attributes(Extractor(c).predict(Product('s','761',title)))
            self.assertEqual(a['storage_gb']['decision'],decision)
            self.assertTrue(all(v['decision']!='auto_accept' for k,v in a.items() if k!='storage_gb'))

    def test_extreme_priors_are_finite_and_bounded(self):
        for score in (0,1,.8):
            n=contextual_score({'score':score,'explicit_role':1,'explicit_unit':1,'cross_field_agreement':1})
            self.assertTrue(0<=n<=1)

    def test_partition_keeps_families_and_normalized_duplicates_together(self):
        rows=[{'sku_id':'1','family_id':'a','title':'Samsung  X1'}, {'sku_id':'2','family_id':'b','title':'samsung x1'}, {'sku_id':'3','family_id':'b','title':'Other X2'}]
        p=partition(rows)
        self.assertEqual(len({(v['group'],v['role']) for v in p.values()}),1)
        self.assertEqual(p,partition(list(reversed(rows))))

    def test_insufficient_data_does_not_fit_and_family_leakage_fails(self):
        pairs=[{'role':role,'group':role,'correct':True} for role in ('fit','calibration','diagnostic')]
        with patch('scripts.research.compare_confidence.fit_logistic',side_effect=AssertionError):
            report,model=learned_comparison(pairs)
        self.assertEqual(report['status'],'insufficient_data');self.assertIsNone(model)
        pairs[1]['group']='fit'
        with self.assertRaisesRegex(ValueError,'leakage'): learned_comparison(pairs)

    def test_offline_logistic_and_platt_are_separate_and_not_runtime_artifacts(self):
        pairs=[]
        for role,n in [('fit',200),('calibration',20),('diagnostic',20)]:
            for i in range(n):
                pairs.append({'role':role,'group':role+str(i),'correct':bool(i%2),'attribute':'brand','category':'761',
                    'features':{'intercept':1.,'score':.85,'explicit_role':float(i%2)}})
        report,model=learned_comparison(pairs)
        self.assertEqual(report['status'],'offline_fitted')
        self.assertEqual(model['runtime_use'],'forbidden')
        self.assertEqual(report['platt']['support'],20)

    def test_experiment_rejects_unreviewed_or_wrong_split_before_prediction(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); ref=root/'reference.jsonl'
            for split,status in [('test_reserved','reviewed'),('development','draft')]:
                ref.write_text(json.dumps({'split':split,'annotation_status':status})+'\n')
                spec=root/'spec.json';spec.write_text(json.dumps({'version':'confidence-experiment-1','seed':SEED,
                    'reference_origin':'ai_assisted_human_reviewed_development','independent_reference':False,
                    'references':[{'path':'reference.jsonl','sha256':hashlib.sha256(ref.read_bytes()).hexdigest()}]}))
                with patch.object(Extractor,'predict',side_effect=AssertionError),self.assertRaises(ValueError): run(spec,root/'output')
                self.assertFalse((root/'output').exists())

    def test_experiment_is_reproducible_keeps_errors_and_rejects_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); ref=root/'reference.jsonl'
            p=Product('synthetic','761','Smartphone Samsung Orbit X82 8/256GB black')
            predicted=Extractor(load_config()).predict(p)
            row=p.as_dict() | {'split':'development','group_id':'synthetic-family','annotation_status':'reviewed',
                'label_source':'manual','annotator':'Synthetic QA','human_review_status':'confirmed','independent_reference':False,
                'attributes':[{'attribute':a['attribute'],'status':'present' if a['value'] is not None and a['attribute']!='brand' else 'absent',
                               'value':a['value'] if a['attribute']!='brand' else None,
                               'unit':a['unit'] if a['attribute']!='brand' else None,
                               'evidence':a['evidence'] if a['attribute']!='brand' else None} for a in predicted['attributes']]}
            ref.write_text(json.dumps(row)+'\n'); original=ref.read_bytes()
            spec=root/'spec.json';spec.write_text(json.dumps({'version':'confidence-experiment-1','seed':SEED,
                'reference_origin':'ai_assisted_human_reviewed_development','independent_reference':False,
                'references':[{'path':'reference.jsonl','sha256':hashlib.sha256(original).hexdigest()}]}))
            r=run(spec,root/'first');run(spec,root/'second')
            self.assertEqual(r['extraction_metrics']['metrics']['micro']['fp'],1)
            self.assertTrue(r['values_evidence_decisions_unchanged'])
            for name in ('report.json','fixed.jsonl','context.jsonl','pairs.private.json'):
                self.assertEqual((root/'first'/name).read_bytes(),(root/'second'/name).read_bytes())
            with self.assertRaises(ValueError): run(spec,root/'first')
            ref.write_text('{}\n')
            with patch.object(Extractor,'predict',side_effect=AssertionError),self.assertRaises(ValueError): run(spec,root/'bad')


@unittest.skipUnless(all(importlib.util.find_spec(n) for n in ('fastapi','httpx','uvicorn')), 'serve/test extras required')
class ConfidenceApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_cli_api_agree_and_profile_changes_fingerprint(self):
        from httpx import ASGITransport, AsyncClient
        from goodsai.api import create_app
        from goodsai.cli import predict
        from goodsai.data import read_predictions
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); config=root/'config.json';config.write_text(json.dumps(profile()))
            product={'schema_version':'0.1','sku_id':'s','category_id':'761','title':'Samsung Orbit X82 8/256GB'}
            source=root/'input.jsonl';source.write_text(json.dumps(product)+'\n')
            output=root/'predictions.jsonl';predict(source,output,profile())
            batch=list(read_predictions(output))[0]
            async with AsyncClient(transport=ASGITransport(app=create_app(str(config))),base_url='http://test') as client:
                response=await client.post('/predict',json=product)
                self.assertEqual(response.status_code,200)
                http=response.json();http['run_id']=batch['run_id'];self.assertEqual(http,batch)
                health=(await client.get('/health')).json()
                self.assertIn('runtime_policy_sha256',health)
            async with AsyncClient(transport=ASGITransport(app=create_app()),base_url='http://test') as client:
                default=(await client.get('/health')).json()
            self.assertNotEqual(health['runtime_policy_sha256'],default['runtime_policy_sha256'])
