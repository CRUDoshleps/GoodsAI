"""QA-006 fixed synthetic grammar. Expectations are authored before inference."""
import random

VERSION = 'qa-006-grammar-v1'
ATTRIBUTES = {
    '761': ('brand', 'model', 'storage_gb', 'ram_gb', 'screen_inches', 'battery_mah', 'color'),
    '482': ('brand', 'model', 'capacity_l', 'power_w', 'color'),
}


def absent(reason='not_found_by_rules'):
    return dict(value=None, unit=None, decision='abstain', evidence=None, reason_codes=[reason])


def generated_cases(seed):
    rng = random.Random(seed)
    cases = []

    def add(name, category, title, description=None, status='processed'):
        row = dict(schema_version='0.1', sku_id=f'generated-{seed}-{name}', category_id=category,
                   title=title, description=description, seller_attributes=[], source_flags=['synthetic'])
        case = {'id': 'generated/' + name, 'input': row,
                'expected': {'status': status, 'attributes': {
                    a: absent() for a in ATTRIBUTES.get(category, ())} if status == 'processed' else {}}}
        cases.append(case)
        return case

    def found(case, attr, value, raw, field='title', unit=None):
        source = case['input'][field]
        start = source.index(raw)
        case['expected']['attributes'][attr] = dict(value=value, unit=unit, decision='review', reason_codes=[],
            evidence=dict(field=field, start=start, end=start + len(raw), text=raw))

    # Fresh commercial names and quantities, not existing fixture SKUs with new IDs.
    for i in range(3):
        brand = rng.choice(['Samsung', 'HONOR', 'Xiaomi'])
        model = rng.choice(['Orbit', 'Vector', 'Nova']) + f' X{rng.randrange(100, 900)}'
        ram, storage = rng.choice([(4, 64), (8, 128), (12, 256), (16, 512)])
        color = rng.choice(['черный', 'белый', 'красный'])
        pair = f'{ram}/{storage}GB'
        c = add(f'phone-title-{i}', '761', f'Смартфон {brand} {model} {pair} {color}')
        for attr, value in [('brand', brand), ('model', model), ('color', color)]:
            found(c, attr, value, value)
        found(c, 'ram_gb', str(ram), pair, unit='GB')
        found(c, 'storage_gb', str(storage), pair, unit='GB')

        model = f'PX-{rng.randrange(1000, 9000)}'
        ml = rng.choice([1200, 1500, 1800, 2000])
        watts = rng.choice([1600, 1800, 2000, 2400])
        cap, power = f'{ml} мл', f'{watts} Вт'
        c = add(f'kettle-title-{i}', '482', f'Чайник Bosch {model} {cap} {power}')
        c['known_issue'] = 21  # Report only; never suppress the missing-model failure.
        found(c, 'brand', 'Bosch', 'Bosch')
        found(c, 'model', model, model)
        found(c, 'capacity_l', str(ml / 1000).rstrip('0').rstrip('.'), cap, unit='L')
        found(c, 'power_w', str(watts), power, unit='W')

    # Explicitly labelled facts in description, with no inferred identity from title.
    for category in ('761', '482'):
        model = f'BX-{rng.randrange(100, 900)}'
        title = 'Смартфон Samsung' if category == '761' else 'Чайник Bosch'
        brand = 'Samsung' if category == '761' else 'Bosch'
        if category == '761':
            battery = rng.choice([4200, 4600, 5200])
            screen = rng.choice(['6,2', '6,4', '6,8'])
            description = f'Модель: {model}; Батарея {battery} мАч. Экран {screen} дюйма.'
        else:
            description = f'Модель: {model}; Объем 1,8 л. Мощность 2,4 кВт.'
        c = add('description-' + category, category, title, description)
        found(c, 'brand', brand, brand)
        found(c, 'model', model, model, 'description')
        if category == '761':
            found(c, 'battery_mah', str(battery), f'{battery} мАч', 'description', 'mAh')
            found(c, 'screen_inches', screen.replace(',', '.'), f'{screen} дюйма', 'description', 'inch')
        else:
            found(c, 'capacity_l', '1.8', '1,8 л', 'description', 'L')
            found(c, 'power_w', '2400', '2,4 кВт', 'description', 'W')

    c = add('html-phone', '761', '😀 Смартфон Samsung',
            '<p>Экран <b>6,4</b>&nbsp;дюйма.</p>')
    found(c, 'brand', 'Samsung', 'Samsung')
    found(c, 'screen_inches', '6.4', '6,4</b>&nbsp;дюйма', 'description', 'inch')
    c = add('html-kettle', '482', '😀 Чайник Bosch', '<p>Объем <b>1,8</b>&nbsp;л.</p>')
    found(c, 'brand', 'Bosch', 'Bosch')
    found(c, 'capacity_l', '1.8', '1,8</b>&nbsp;л', 'description', 'L')

    c = add('conflict', '761', 'Смартфон Samsung черный', 'Цвет: белый.')
    found(c, 'brand', 'Samsung', 'Samsung')
    c['expected']['attributes']['color'] = absent('conflicting_evidence')
    c = add('negation', '482', 'Чайник Bosch', 'Объем не 1,8 л.')
    found(c, 'brand', 'Bosch', 'Bosch')
    add('missing', '761', 'Смартфон', 'Сведения не представлены.')
    add('unsupported', 'unseen-category', 'Товар произвольной категории', status='unsupported_category')
    c = add('invalid-product', '761', 'Смартфон', status='invalid_input')
    c['input']['seller_attributes'] = [{'name': 'brand', 'value': 'forbidden-hint'}]
    # A valid row after the invalid row proves the batch did not silently truncate.
    c = add('after-invalid', '482', 'Чайник Bosch')
    found(c, 'brand', 'Bosch', 'Bosch')
    return cases
