"""Invented two-category shadow demo. Generates blank forms, never human answers."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from goodsai.attribute_shadow import default_plan
from goodsai.config import load_config
from goodsai.contracts import Product
from goodsai.data import digest
from goodsai.silver_prepare import VERSION, assemble
from scripts.research.audit_splits import dump, write_rows
from scripts.research.attribute_shadow import prepare


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    root = args.output_dir.resolve()
    if root.exists():
        parser.error("Use a new demo output directory")
    root.mkdir(parents=True, mode=0o700)
    source = root / "source"
    source.mkdir(mode=0o700)
    config = load_config()
    rows, catalog, members = [], {}, {}
    for i, (ram, storage, color) in enumerate(((4, 64, 'белый'), (8, 256, 'черный'), (12, 512, 'синий'))):
        phone = Product(f'invented-phone-{i}', '761', f'Смартфон Samsung Orbit X7{i} {ram}/{storage}GB {color}',
                        'Экран 6,4 дюйма. Аккумулятор 4600 мАч.')
        kettle = Product(f'invented-kettle-{i}', '482', f'Чайник Bosch KX-8{i} 1,7 л 2200 Вт {color}')
        for p in (phone, kettle):
            rows.append(p.as_dict())
            members[p.sku_id] = {'family_id': p.sku_id + '-family', 'split': 'development', 'quarantine_reasons': []}
            catalog[p.sku_id] = {'category_id': p.category_id, 'params': []}
        catalog[phone.sku_id]['params'] = [
            {'@name': 'Встроенная память (ROM)_search', '#text': str(storage), '@unit': 'GB'}]
    inputs, refs, metadata, _ = assemble(rows, catalog, members, config)
    for name, values in [('input.jsonl', inputs), ('reference.jsonl', refs), ('metadata.jsonl', metadata)]:
        write_rows(source / name, values)
    for name in ['train.jsonl', 'support_review.blank.jsonl', 'llm_screening.input.jsonl']:
        write_rows(source / name, [])
    dump(source / 'train.split.json', {})
    dump(source / 'policy.json', {'config': config})
    dump(source / 'manifest.json', {'version': VERSION, 'reference_kind': 'catalog_silver',
                                  'protected_text_exported': False,
                                  'artifacts': {p.name: digest(p) for p in source.iterdir()}})
    plan = default_plan(config)
    # Demonstrate separate targets; these are invented scenario settings only.
    for p in plan['policies']:
        if p['attribute'] in {'ram_gb', 'storage_gb'}:
            p['target_precision'] = .97
    dump(root / 'plan.json', plan)
    report = prepare(source, root / 'plan.json', root / 'audit', reviewer='synthetic-demo-not-real-quality')
    for p in source.iterdir():
        p.chmod(0o600)
    (root / 'plan.json').chmod(0o600)
    print(json.dumps({'synthetic_only': True, 'real_quality': None, 'cards': report['cards'],
                      'fields': len(report['fields']), 'audit_tasks': report['audit_tasks'],
                      'human_answers_generated': False, 'runtime_auto_accept_changed': False,
                      'review': str(root / 'audit' / 'review.html')}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
