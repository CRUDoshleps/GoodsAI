from copy import deepcopy
from dataclasses import replace
import unittest
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
from goodsai.contracts import load_config,Product
from goodsai.verify import Extractor
from goodsai.drift import snapshot,compare,DriftPolicy,js_divergence


class DriftTests(unittest.TestCase):
    def test_cli_binds_snapshot_to_the_actual_producer_config(self):
        from goodsai.cli import predict
        from goodsai.drift import main
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'input.jsonl';output=root/'predictions.jsonl'
            product=Product('synthetic','482','Чайник Polaris 1.7 л',source_flags=('synthetic',))
            source.write_text(json.dumps(product.as_dict())+'\n',encoding='utf-8')
            predict(source,output,self.config)
            args=['drift','snapshot','--input',str(source),'--predictions',str(output),
                  '--manifest',str(root/'predictions.manifest.json'),'--output',str(root/'snapshot.json')]
            with patch('sys.argv',args):main()
            self.assertEqual(json.loads((root/'snapshot.json').read_text(encoding='utf-8'))['count'],1)
            changed=deepcopy(self.config);changed['brands']['Samsung'].append('Самсунг')
            config=root/'changed.json';config.write_text(json.dumps(changed),encoding='utf-8')
            with patch('sys.argv',args+['--config',str(config)]):
                with self.assertRaisesRegex(ValueError,'configuration differs'):main()

    def setUp(self):
        self.config=load_config();self.identity={'schema':'0.1','config_sha256':'a'*64,
            'policy_sha256':'b'*64,'producer_sha256':'c'*64}
        self.policy=DriftPolicy(min_support=20,rate_delta=.15,js_threshold=.2,persistence=2)

    def stream(self,unsupported=0,blank=False,batch='d',n=200):
        p=Product('secret-sku','482' if not unsupported else '999-secret-category',
                  'Чайник Kitfort KT-1 1.7 л 2100 Вт черный' if not blank else 'Чайник', 'secret text')
        products=[replace(p,sku_id=f'secret-sku-{i}') for i in range(n)]
        rows=[Extractor(self.config).predict(p) for p in products]
        return snapshot(products,rows,self.config,self.identity,batch*64)

    def test_stationary_stream_no_false_alarm_and_duplicate_does_not_advance(self):
        base=self.stream();cur=self.stream(batch='e')
        report,state=compare(base,cur,self.policy)
        self.assertFalse(report['alerts'])
        repeat,state2=compare(base,cur,self.policy,state)
        self.assertTrue(repeat['duplicate_window']);self.assertEqual(state,state2)

    def test_persistent_unsupported_shift_alerts_once_and_recovers_with_hysteresis(self):
        base=self.stream()
        first,state=compare(base,self.stream(unsupported=1,batch='e'),self.policy)
        self.assertFalse(first['alerts'])
        second,state=compare(base,self.stream(unsupported=1,batch='f'),self.policy,state)
        self.assertTrue(second['alerts'])
        self.assertTrue(all(a['action'] and a['aggregate_source'] for a in second['alerts']))
        third,state=compare(base,self.stream(unsupported=1,batch='a'),self.policy,state)
        self.assertFalse(third['alerts'])
        recovered,state=compare(base,self.stream(batch='b'),self.policy,state)
        self.assertTrue(recovered['resolved'])

    def test_small_groups_and_incompatible_policy_are_not_data_drift(self):
        base=self.stream(n=5);report,_=compare(base,self.stream(blank=True,batch='e',n=5),self.policy)
        self.assertFalse(report['alerts']);self.assertTrue(report['suppressed'])
        cur=self.stream(batch='f');cur['identity']['policy_sha256']='f'*64
        with self.assertRaisesRegex(ValueError,'Incompatible'):compare(self.stream(),cur,self.policy)

    def test_snapshot_redacts_all_untrusted_content_and_quality_is_unavailable(self):
        value=self.stream(unsupported=1)
        self.assertNotIn('secret',str(value));self.assertIsNone(value['quality']['f1'])
        self.assertEqual(value['categories'],{'__other__':200})
        self.assertEqual(js_divergence({'a':1},{'a':1}),0)
        self.assertEqual(js_divergence({'a':1},{'b':1}),1)
        damaged=deepcopy(value);damaged['cohorts']['__all__']['unsupported']=999
        with self.assertRaises(ValueError):compare(value,damaged,self.policy)

    def test_abstain_perturbation_and_invalid_thresholds(self):
        base=self.stream();_,state=compare(base,self.stream(blank=True,batch='e'),self.policy)
        report,_=compare(base,self.stream(blank=True,batch='f'),self.policy,state)
        self.assertTrue(any('abstain' in a['signal'] for a in report['alerts']))
        for values in ({'min_support':1},{'rate_delta':float('nan')},{'persistence':True}):
            with self.assertRaises(ValueError):DriftPolicy(**({'min_support':20,'rate_delta':.15,'js_threshold':.2,'persistence':2}|values))


if __name__=='__main__':unittest.main()
