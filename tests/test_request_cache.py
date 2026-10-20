from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from goodsai.llm import LLMExtractor, LLMSettings, cache_key
from goodsai.request_cache import ExactCache, SingleFlight, audit
from goodsai.contracts import load_config, Product
from test_llm import PHONE, FakeProvider, answer, attrs


class ExactRequestTests(unittest.TestCase):
    def test_exact_fingerprint_and_namespace_mutations(self):
        config, settings = load_config(), LLMSettings(model='m')
        key = cache_key(PHONE, ['brand'], config, settings)
        self.assertEqual(key, cache_key(replace(PHONE, sku_id='different-sku'), ['brand'], config, settings))
        for product in (replace(PHONE, title=PHONE.title+' нет'), replace(PHONE, category_id='482'),
                        replace(PHONE, description=(PHONE.description or '')+'X'), replace(PHONE, source_flags=('private',))):
            self.assertNotEqual(key, cache_key(product, ['brand'], config, settings))
        for changed in (replace(settings, model='next'), replace(settings, model_revision='r2'),
                        replace(settings, cache_namespace='other'), replace(settings, max_tokens=1024)):
            self.assertNotEqual(key, cache_key(PHONE, ['brand'], config, changed))
        # Even content beyond the provider's truncation limit must invalidate.
        long = replace(PHONE, description='x'*7000)
        self.assertNotEqual(cache_key(long, ['brand'], config, settings),
                            cache_key(replace(long, description='x'*6999+'y'), ['brand'], config, settings))

    def test_ttl_corruption_and_unavailable_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            clock=[0]
            cache=ExactCache(Path(folder), 10, lambda:clock[0]);key='a'*64
            cache.put(key, [], {})
            self.assertIsNotNone(cache.get(key))
            clock[0]=10;self.assertIsNone(cache.get(key))
            cache._path(key).write_text('{broken',encoding='utf-8')
            self.assertIsNone(cache.get(key))
            unavailable=Path(folder)/'file';unavailable.write_text('not a directory')
            provider=FakeProvider(answer(('brand','Zorion','Zorion')))
            row=LLMExtractor(load_config(),provider,LLMSettings(model='m',cache_dir=unavailable)).predict(PHONE)
            self.assertEqual(attrs(row)['brand']['value'],'Zorion')

    def test_concurrent_duplicates_billed_once_and_each_sku_gets_result(self):
        with tempfile.TemporaryDirectory() as folder:
            class Slow(FakeProvider):
                def complete(self,*args):
                    time.sleep(.08)
                    return super().complete(*args)
            provider=Slow(answer(('brand','Zorion','Zorion')))
            settings=LLMSettings(model='m', cache_dir=Path(folder))
            ex=LLMExtractor(load_config(),provider,settings)
            with ThreadPoolExecutor(max_workers=6) as pool:
                rows=list(pool.map(ex.predict,[replace(PHONE,sku_id=f'sku-{i}') for i in range(6)]))
            self.assertEqual(provider.calls,1)
            self.assertEqual(ex.report()['attempts'],1)
            self.assertEqual(len({r['sku_id'] for r in rows}),6)
            self.assertTrue(all(attrs(r)['brand']['value']=='Zorion' for r in rows))
            self.assertEqual(ex.report()['singleflight_hits'],5)
            warm=LLMExtractor(load_config(),provider,settings);warm.predict(PHONE)
            self.assertEqual((warm.report()['calls'],warm.report()['prompt_tokens'],warm.report()['cache_hits']),(0,0,1))

    def test_singleflight_failure_wakes_waiter_and_allows_retry(self):
        flight=SingleFlight();started=threading.Event();release=threading.Event()
        def leader():
            started.set();release.wait(1);raise RuntimeError('private payload')
        with ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(flight.run,'key',leader,1);started.wait(1)
            second=pool.submit(flight.run,'key',lambda:([],None),1)
            time.sleep(.02);release.set()
            with self.assertRaises(RuntimeError):first.result()
            self.assertEqual(second.result(),((None,'llm_leader_failed'),True))
        self.assertEqual(flight.run('key',lambda:([],None),1),(([],None),False))

    def test_hit_rechecks_gate_and_audit_has_no_keys_or_text(self):
        with tempfile.TemporaryDirectory() as folder:
            provider=FakeProvider(answer(('brand','Zorion','Zorion')))
            settings=LLMSettings(model='m',cache_dir=Path(folder))
            ex=LLMExtractor(load_config(),provider,settings);ex.predict(PHONE)
            class Gate:
                def reason(self,candidate):return 'verifier_test_rejection'
            class Factory:
                def create(self,product):return Gate()
            row=LLMExtractor(load_config(),provider,settings,gate_factory=Factory()).predict(PHONE)
            self.assertIsNone(attrs(row)['brand']['value'])
            report=audit([PHONE, replace(PHONE,sku_id='other')],load_config(),settings)
            self.assertEqual((report['potentially_avoided_calls'],report['actual_calls']),(1,0))
            self.assertNotIn('Zorion',str(report))


if __name__=='__main__':unittest.main()
