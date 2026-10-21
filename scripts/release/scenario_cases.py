"""SPEC-002 source-authored policy probes; never derive expectations from predictions."""
import random

from scripts.release.external_cases import ATTRIBUTES


def policy_cases(seed):
    rng = random.Random(seed)
    cases = []

    def add(name, category, title, description=None):
        row = dict(schema_version='0.1', sku_id=f'matrix-{seed}-{name}', category_id=category,
                   title=title, description=description, seller_attributes=[], source_flags=['synthetic'])
        # Reasons may differ between a conservative source and a gate. Abstain
        # still requires nonempty reasons through the real prediction validator.
        case = dict(id='matrix/' + name, input=row, expected=dict(status='processed', attributes={
            a: dict(value=None, unit=None, decision='abstain', evidence=None) for a in ATTRIBUTES[category]}))
        cases.append(case)
        return case

    def found(case, attr, value, quote, field='title', unit=None):
        start = case['input'][field].index(quote)
        case['expected']['attributes'][attr] = dict(value=value, unit=unit, decision='review', reason_codes=[],
            evidence=dict(field=field, start=start, end=start + len(quote), text=quote))

    model = f'Orbit Q{rng.randrange(100, 900)}'
    c = add('subbrand', '761', f'Смартфон Xiaomi Redmi {model} 8/128GB')
    found(c, 'brand', 'Redmi', 'Redmi')
    found(c, 'model', model, model)
    found(c, 'ram_gb', '8', '8/128GB', unit='GB')
    found(c, 'storage_gb', '128', '8/128GB', unit='GB')

    model = f'Galaxy Q{rng.randrange(100, 900)} Pro 5G'
    c = add('model-network', '761', f'Смартфон Samsung {model} 12/256GB')
    found(c, 'brand', 'Samsung', 'Samsung')
    found(c, 'model', model, model)
    found(c, 'ram_gb', '12', '12/256GB', unit='GB')
    found(c, 'storage_gb', '256', '12/256GB', unit='GB')

    for name, title, description in [
        ('single-memory', 'Смартфон Samsung', 'Память 128 GB.'),
        ('missing-unit', 'Смартфон Samsung 8/256', None),
        ('typo-unit', 'Смартфон Samsung 12+512G', None),
    ]:
        c = add(name, '761', title, description)
        found(c, 'brand', 'Samsung', 'Samsung')

    c = add('ambiguous-code', '482', f'Чайник Bosch QX-{rng.randrange(100, 900)}/BL')
    found(c, 'brand', 'Bosch', 'Bosch')

    c = add('marketing-color', '761', 'Смартфон Samsung Prestige Gold')
    found(c, 'brand', 'Samsung', 'Samsung')
    found(c, 'color', 'золотой', 'Prestige Gold')

    c = add('wrong-capacity-unit', '482', 'Чайник Bosch', 'Объем 1,7 кг.')
    found(c, 'brand', 'Bosch', 'Bosch')

    c = add('auxiliary-power', '482', 'Чайник Bosch', 'Мощность подогрева 300 Вт.')
    found(c, 'brand', 'Bosch', 'Bosch')

    model = f'PX-{rng.randrange(1000, 9000)}'
    c = add('kettle-color', '482', f'Чайник Bosch {model} 1,7 л 2200 Вт белый')
    for attr, value in [('brand', 'Bosch'), ('model', model), ('color', 'белый')]:
        found(c, attr, value, value)
    found(c, 'capacity_l', '1.7', '1,7 л', unit='L')
    found(c, 'power_w', '2200', '2200 Вт', unit='W')
    return cases
