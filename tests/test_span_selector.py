from dataclasses import replace
import json
import unittest
from goodsai.contracts import Product, load_config
from goodsai.llm import LLMExtractor, LLMSettings, ProviderResponse
from goodsai.span_selector import candidate_from_id, selector_index, selector_payload
from test_llm import attrs


class SelectorTests(unittest.TestCase):
    def setUp(self):
        self.p=Product('x','761','Смартфон Zorion QX-900','Батарея 5000 мА*ч.')
        self.config=load_config()

    def selected(self,field,surface):
        index,_=selector_index(self.p)
        return next(e.span_id for e in index.entries if e.field==field and e.surface==surface)

    def test_values_come_only_from_ids_and_exact_original_offsets(self):
        for attr,field,text,expected in [('brand','title','Zorion','Zorion'),
                                          ('battery_mah','description','5000 мА*ч','5000')]:
            candidate,reason=candidate_from_id(self.p,{'attribute':attr,'span_id':self.selected(field,text)},self.config)
            self.assertIsNone(reason)
            self.assertEqual(candidate.value,expected)
            self.assertEqual(getattr(self.p,field)[candidate.start:candidate.end],candidate.text)

    def test_free_value_unknown_stale_and_null_are_strictly_checked(self):
        valid={'attribute':'brand','span_id':self.selected('title','Zorion')}
        self.assertEqual(candidate_from_id(self.p,valid|{'value':'Apple'},self.config)[1],'llm_selector_bad_shape')
        self.assertIn('stale',candidate_from_id(replace(self.p,title=self.p.title+' changed'),valid,self.config)[1])
        self.assertIn('stale',candidate_from_id(self.p,valid|{'span_id':'invalid'},self.config)[1])
        self.assertEqual(candidate_from_id(self.p,{'attribute':'brand','span_id':None},self.config),(None,None))

    def test_selector_provider_uses_enum_and_shared_gate(self):
        p=self.p
        class Provider:
            model='fake'
            def complete(inner,messages,max_tokens):
                payload=json.loads(messages[1]['content'])
                self.assertIs(payload['server_constrained_decoding'],False)
                self.assertIn('response_schema',payload)
                selected=next(e['span_id'] for e in payload['spans'] if e['text']=='Zorion')
                return ProviderResponse(json.dumps({'attributes':[{'attribute':'brand','span_id':selected}]}))
        row=LLMExtractor(self.config,Provider(),LLMSettings(model='fake',span_selector=True)).predict(p)
        self.assertEqual((attrs(row)['brand']['value'],attrs(row)['brand']['decision']),('Zorion','review'))

    def test_incomplete_index_abstains_without_call(self):
        class Never:
            model='fake'
            def complete(self,*args):raise AssertionError('must not call')
        row=LLMExtractor(self.config,Never(),LLMSettings(model='fake',span_selector=True,selector_max_spans=1)).predict(self.p)
        self.assertIn('llm_selector_index_incomplete',attrs(row)['brand']['reason_codes'])

    def test_selected_negated_evidence_is_rejected_on_full_original(self):
        self.p=replace(self.p,description='Без батареи 5000 мА*ч.')
        candidate,reason=candidate_from_id(self.p,{'attribute':'battery_mah','span_id':self.selected('description','5000 мА*ч')},self.config)
        self.assertIsNone(candidate)
        self.assertIsNotNone(reason)


if __name__=='__main__':unittest.main()
