"""VER-001: proper names are not product colors; same guard for rules/source/LLM."""
import json
from pathlib import Path
import tempfile
import unittest

from goodsai.contracts import Product, load_config, validate_prediction
from goodsai.llm import ground
from goodsai.relation import RelationVerifier
from goodsai.rules import Candidate
from goodsai.verify import Extractor


class ColorAttachmentTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()
        self.extractor = Extractor(self.config)

    def color(self, title, description=None, category='482'):
        p = Product('synthetic-color', category, title, description)
        result = self.extractor.predict(p)
        validate_prediction(result, self.config, p)
        return next(a for a in result['attributes'] if a['attribute'] == 'color')

    def test_name_token_is_rejected_without_manufacturer_lookup(self):
        for title in ['Электрочайник RED SOLUTION ZZ-905', 'Чайник BLUE HARBOR QX-728',
                      'Чайник <b>RED</b> SOLUTION ZZ-905']:
            with self.subTest(title=title):
                got = self.color(title)
                self.assertIsNone(got['value'])
                self.assertEqual(got['reason_codes'], ['relation_name_token'])

    def test_color_word_inside_model_and_explicit_name_label_is_not_color(self):
        for title, desc, category in [
            ('Смартфон Samsung Black X721', None, '761'),
            ('Чайник Bosch', 'Модель: Red Star K721.', '482'),
            ('Чайник Bosch', 'Бренд: BLUE HARBOR;', '482'),
        ]:
            p = Product('synthetic-name', category, title, desc)
            field = 'description' if desc else 'title'
            quote, canonical = ('Black', 'черный') if not desc else (('Red', 'красный') if 'Red' in desc else ('BLUE', 'синий'))
            candidate = Candidate('color', canonical, None, field, getattr(p, field).index(quote),
                                  getattr(p, field).index(quote) + len(quote), quote, .75, 'synthetic')
            self.assertEqual(RelationVerifier(p, self.config).reason(candidate), 'relation_name_token')
            self.assertEqual(ground(p, 'color', canonical, quote, self.config), (None, 'relation_name_token'))

    def test_independent_color_survives_and_conflict_policy_is_unchanged(self):
        for title, desc, expected in [
            ('Чайник RED SOLUTION ZZ-905 черный', None, 'черный'),
            ('Чайник BLUE HARBOR QX-728', 'Цвет корпуса: белый.', 'белый'),
            ('Чайник Bosch красный', None, 'красный'),
            ('Чайник Bosch', 'Материал корпуса: сталь; цвет: серебристый.', 'серебристый'),
            ('Чайник Bosch', 'Модель: QX-721. Цвет: черный.', 'черный'),
            ('Чайник Bosch', 'Модель: QX-721 цвет: черный.', 'черный'),
        ]:
            got = self.color(title, desc)
            self.assertEqual(got['value'], expected)
            self.assertEqual(got['decision'], 'review')
        got = self.color('Чайник RED SOLUTION ZZ-905 черный', 'Цвет корпуса: белый.')
        self.assertIsNone(got['value'])
        self.assertEqual(got['reason_codes'], ['conflicting_evidence'])

    def test_material_context_does_not_become_color(self):
        got = self.color('Чайник Bosch', 'Материал корпуса: серебристый металл.')
        self.assertIsNone(got['value'])
        self.assertEqual(got['reason_codes'], ['relation_material_not_color'])

    def test_unknown_compound_is_not_reduced_to_basic_color_by_llm(self):
        p = Product('synthetic-shade', '482', 'Чайник Bosch', 'Цвет: неоново-черный.')
        self.assertEqual(ground(p, 'color', 'черный', 'черный', self.config),
                         (None, 'relation_unknown_color_modifier'))

    def test_llm_values_also_pass_negation_accessory_and_foreign_entity_guard(self):
        for text, expected in [
            ('Цвет черный у чехла.', 'relation_other_object'),
            ('Совместим с телефоном: цвет черный.', 'relation_foreign_entity'),
            ('В комплекте чехол: цвет черный.', 'relation_bundle_item'),
            ('Нет цвета черный.', 'llm_uncertain_context'),
        ]:
            p = Product('synthetic-llm-color', '482', 'Чайник Bosch', text)
            self.assertEqual(ground(p, 'color', 'черный', 'черный', self.config), (None, expected))

    def test_cli_and_api_expose_same_rejection_and_preserve_independent_color(self):
        from fastapi.testclient import TestClient
        from goodsai.api import create_app
        from goodsai.cli import predict
        p = Product('synthetic-parity', '482', 'Чайник RED SOLUTION ZZ-905', 'Цвет: черный.')
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder) / 'input.jsonl', Path(folder) / 'predictions.jsonl'
            source.write_text(json.dumps(p.as_dict()) + '\n', encoding='utf-8')
            predict(source, output, self.config)
            row = json.loads(output.read_text(encoding='utf-8'))
        with TestClient(create_app()) as client:
            response = client.post('/predict', json=p.as_dict())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(row['attributes'], response.json()['attributes'])
        self.assertEqual(next(a for a in row['attributes'] if a['attribute'] == 'color')['value'], 'черный')


if __name__ == '__main__':
    unittest.main()
