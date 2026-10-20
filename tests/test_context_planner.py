from dataclasses import replace
import json
import unittest
from goodsai.context_planner import plan_context, source_blocks
from goodsai.contracts import Product, load_config
from goodsai.llm import build_messages, LLMSettings, LLMExtractor, cache_key
from test_llm import PHONE, FakeProvider, answer


class ContextPlannerTests(unittest.TestCase):
    def test_original_blocks_partition_html_and_unicode_and_reduced_plan_retains_support(self):
        p=Product('x','482','Чайник Vexa', '<p>История бренда.</p>'*8+'<p>Мощность 2100 Вт.</p>'+'<p>Упаковка.</p>'*8)
        blocks=source_blocks(p)
        self.assertEqual(''.join(b.text for b in blocks if b.field=='description'),p.description)
        plan=plan_context(p,['power_w'])
        self.assertEqual(plan.status,'reduced')
        self.assertLess(plan.selected_chars,plan.original_chars)
        self.assertIn('2100 Вт',''.join(b.text for b in plan.blocks))
        for b in plan.blocks:self.assertEqual(b.text,getattr(p,b.field)[b.start:b.end])

    def test_negation_foreign_entity_conflict_and_cross_sentence_reference_use_full_context(self):
        for description in ('Объём 1.7 л. Нет такого объёма.', 'Карта microSD 256 GB.',
                            'Для другого товара 2100 Вт.', 'Мощность 2100 Вт. Мощность 1800 Вт.',
                            'Мощность 2100 Вт. Она указана ошибочно.'):
            p=Product('x','482','Чайник Vexa',description)
            plan=plan_context(p,['power_w','capacity_l'])
            self.assertEqual(plan.status,'full',description)
            self.assertEqual(plan.selected_chars,plan.original_chars)

    def test_unknown_scanner_and_budget_fail_closed(self):
        p=replace(PHONE,description='не '+ 'x'*18000)
        self.assertEqual(plan_context(p,['brand'],262144).status,'full')
        self.assertEqual(plan_context(p,['brand'],128).status,'unavailable')
        provider=FakeProvider(answer())
        ex=LLMExtractor(load_config(),provider,LLMSettings(model='m',context_planner=True,context_max_chars=128))
        row=ex.predict(p)
        self.assertEqual(provider.calls,0)
        self.assertTrue(any('llm_context_budget_exceeded' in a['reason_codes'] for a in row['attributes']))

    def test_messages_use_only_exact_blocks_and_cache_is_invalidated(self):
        config=load_config();settings=LLMSettings(model='m',context_planner=True)
        messages=build_messages(PHONE,['battery_mah'],config,settings)
        payload=json.loads(messages[1]['content'])
        for b in payload['source_blocks']:
            self.assertEqual(b['text'],getattr(PHONE,b['field'])[b['start']:b['end']])
        self.assertNotEqual(cache_key(PHONE,['battery_mah'],config,settings),
                            cache_key(PHONE,['battery_mah'],config,replace(settings,context_planner=False)))


if __name__=='__main__':unittest.main()
