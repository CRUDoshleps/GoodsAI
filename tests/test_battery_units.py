"""BASE-003 unit grammar and exact evidence; relation cases rely on VER-001."""
import re
import unittest

from goodsai.contracts import Product, load_config, validate_prediction
from goodsai.normalize import NUMBER
from goodsai.verify import Extractor


class BatteryUnitsTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()
        self.extractor = Extractor(self.config)

    def predict(self, description, category='761', title='Смартфон Samsung QA-901 8/256GB'):
        product = Product('synthetic-battery', category, title, description)
        row = self.extractor.predict(product)
        validate_prediction(row, self.config, product)
        return {a['attribute']:a for a in row['attributes']}, product

    def test_explicit_units_and_raw_evidence(self):
        for unit in ['мА*ч','мА·ч','мА⋅ч','мАч','мА ч','мА * ч','мА\u00a0⋅\u202fч',
                     'мa*ч','ма*Ч','mAh','MAH']:
            with self.subTest(unit=unit):
                attrs,p = self.predict('Ёмкость аккумулятора 5100 '+unit+'.')
                a = attrs['battery_mah']; e = a['evidence']
                self.assertEqual((a['value'],a['unit'],a['decision']),('5100','mAh','review'))
                self.assertEqual(e['text'],'5100 '+unit)
                self.assertEqual(p.description[e['start']:e['end']],e['text'])

    def test_inline_html_and_entities_map_to_original(self):
        attrs,p = self.predict('Батарея <b>5100</b> мА&#42;ч.')
        a = attrs['battery_mah'];e = a['evidence']
        self.assertEqual(a['value'],'5100')
        self.assertEqual(e['text'],'5100</b> мА&#42;ч')
        self.assertEqual(p.description[e['start']:e['end']],e['text'])

    def test_units_cannot_cross_hidden_or_block_boundaries(self):
        for text in ['Батарея 5100 мА<br>*ч','Батарея 5100 мА<script>x</script>*ч']:
            with self.subTest(text=text):
                self.assertIsNone(self.predict(text)[0]['battery_mah']['value'])

    def test_other_objects_do_not_become_battery(self):
        for text in ['В комплекте внешний аккумулятор 10000 мА*ч.',
                     'Аккумулятор другого смартфона 5100 мА⋅ч.',
                     'Для смартфона Samsung аккумулятор 5100 мА*ч.']:
            with self.subTest(text=text):
                self.assertIsNone(self.predict(text)[0]['battery_mah']['value'])

    def test_negation_ranges_bounds_and_wrong_dimensions(self):
        for text in ['Аккумулятор не 5100 мА*ч.', 'Аккумулятор от 5000 до 5100 мА*ч.',
                     'Аккумулятор 499 мА*ч.', 'Аккумулятор 31 000 мА⋅ч.',
                     'Аккумулятор 5100 мВт*ч.', 'Аккумулятор 5100 мА**ч.',
                     'Аккумулятор 5100 мА*час.', 'Номер упаковки 5100 мА*ч.']:
            with self.subTest(text=text):
                self.assertIsNone(self.predict(text)[0]['battery_mah']['value'])

    def test_conflicting_capacities_still_abstain(self):
        a = self.predict('Аккумулятор 5100 мА*ч или батарея 6000 мА⋅ч.')[0]['battery_mah']
        self.assertIsNone(a['value'])
        self.assertEqual(a['reason_codes'],['conflicting_evidence'])

    def test_nonbattery_attributes_unchanged_in_pattern_ablation(self):
        before = Extractor(self.config)
        before.rules.patterns['battery_mah'] = re.compile(
            rf'(?<![\w.,])(?P<n>{NUMBER})\s*(?P<u>м[аa][·\s]*ч|mAh)(?!\w)',re.I)
        for p in [Product('s','761','Samsung QA-901 8/256GB black','Экран 6,5 дюйма. Аккумулятор 5100 мА*ч.'),
                  Product('k','482','Чайник Bosch QA-902 1,7 л 2200 Вт белый')]:
            left = [a for a in before.predict(p)['attributes'] if a['attribute']!='battery_mah']
            right = [a for a in self.extractor.predict(p)['attributes'] if a['attribute']!='battery_mah']
            self.assertEqual(left,right)


if __name__ == '__main__': unittest.main()
