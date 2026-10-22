"""Fixed, offline storage acceptance audit. Never emits runtime auto_accept."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))

from goodsai.cli import predict
from goodsai.contracts import Product, load_config, validate_prediction
from goodsai.data import digest, read_jsonl, read_predictions
from goodsai.normalize import numeric
from goodsai.runtime import identity
from goodsai.silver_calibration import calibrate
from goodsai.silver_evaluate import evaluate_rows, fraction
from goodsai.silver_prepare import verify_bundle, unique
from scripts.research.audit_splits import dump, exposure_ids, require, write_rows
from scripts.research.human_gold import TEMPLATE, checked, evidence, new_directory, seal
from scripts.research.review_m2 import fence

PROTOCOL = ROOT / 'docs/STORAGE_SHADOW.md'
POLICY = {
    'version': 'storage-shadow-1', 'seed': 'goodsai-storage-shadow-20261022-v1',
    'category_id': '761', 'attribute': 'storage_gb', 'unit': 'GB',
    'rule_ids': ['memory.context.v1', 'memory.title-pair.v1'],
    'audit_families': 300, 'batch_size': 50, 'confidence_level': .95,
    'target_precision': .99, 'raw_score_diagnostics': [0, .75, .8, .85, .9, .95, 1],
    'runtime_auto_accept': False, 'independent_reference': False,
    'human_review': 'human_verified_rule_proposals_not_blind_gold',
}
PHONE = re.compile(r'\b(?:смартфон\w*|smartphone)\b', re.I)
OTHER = re.compile(r'\b(?:часы|часов|браслет\w*|чех\w*|пленк\w*|плёнк\w*|case|watch|cover)\b', re.I)
ROLES = {'fit', 'calibration', 'diagnostic', 'development_feedback'}


def rank(namespace, value):
    return hashlib.sha256(f"{POLICY['seed']}:{namespace}:{value}".encode()).hexdigest()


def select_reason(product, prediction, config):
    """Only runtime-available text/candidates. No catalog, gold or SKU features."""
    validate_prediction(prediction, config, product)
    if product.category_id != '761' or prediction['status'] != 'processed':
        return 'outside_category'
    if not PHONE.search(product.title) or OTHER.search(product.title):
        return 'title_category_not_explicit_or_accessory'
    attrs = {a['attribute']: a for a in prediction['attributes']}
    a = attrs['storage_gb']
    if a['decision'] != 'review':
        return 'no_storage_candidate'
    if a['method'] != 'rule' or a['unit'] != 'GB' or a['rule_id'] not in POLICY['rule_ids'] or a['reason_codes']:
        return 'outside_fixed_policy'
    if any('conflicting_evidence' in attrs[k]['reason_codes'] for k in ['storage_gb', 'ram_gb']):
        return 'memory_conflict'
    return None


def family_sample(candidates, metadata, seen):
    blocked = {m['family_id'] for s, m in metadata.items() if m.get('exposed') or s in seen}
    grouped = defaultdict(list)
    for row in candidates:
        if metadata[row['sku_id']]['family_id'] not in blocked:
            grouped[metadata[row['sku_id']]['family_id']].append(row)
    selected = []
    for family in sorted(grouped, key=lambda f: rank('family', f))[:POLICY['audit_families']]:
        row = min(grouped[family], key=lambda r: rank('sku', r['sku_id']))
        selected.append(row | {'family_id': family, 'task_id': f'S{len(selected)+1:03}'})
    return selected, len(grouped), len(blocked)


def precision_lower(correct, total, alpha=.05):
    """Exact one-sided binomial lower bound; caller must disclose assumptions."""
    require(type(correct) is int and type(total) is int and 0 <= correct <= total,
            'invalid_binomial_counts')
    require(type(alpha) in (float, int) and 0 < alpha < 1, 'invalid_alpha')
    if not total:
        return None
    if correct == 0:
        return 0.
    if correct == total:
        return alpha ** (1 / total)
    coefficients = [(k, math.lgamma(total+1)-math.lgamma(k+1)-math.lgamma(total-k+1))
                    for k in range(correct, total+1)]
    lo, hi = 0., 1.
    for _ in range(70):
        p = (lo+hi)/2
        logs = [c+k*math.log(p)+(total-k)*math.log1p(-p) for k,c in coefficients]
        maximum = max(logs)
        tail = math.exp(maximum) * sum(math.exp(x-maximum) for x in logs)
        if tail < alpha:
            lo = p
        else:
            hi = p
    return (lo+hi)/2


def tool_hashes():
    paths = [Path(__file__), PROTOCOL, TEMPLATE,
             ROOT/'scripts/research/human_gold.py', ROOT/'scripts/research/audit_splits.py',
             ROOT/'scripts/research/review_m2.py']
    return {str(p.relative_to(ROOT)): digest(p) for p in paths}


def sources_unchanged(freeze):
    require(all(digest(Path(p)) == h for p,h in freeze['source_hashes'].items()), 'source_changed')
    require(tool_hashes() == freeze['tool_hashes'], 'tool_changed_after_freeze')
    now = identity(load_config())
    require(all(now[k] == freeze['runtime'][k] for k in ['code_sha256', 'config_sha256']),
            'runtime_changed_after_freeze')


def review_html(payload):
    text = TEMPLATE.read_text(encoding='utf-8')
    text = text.replace('GoodsAI — независимая ручная разметка', 'GoodsAI — проверка предложений правил')
    start, end = text.index('<p>Только исходные тексты.'), text.index('<p id="identity">')
    text = text[:start] + (
        '<p>Значение и цитата предзаполнены детерминированными правилами. '
        'Статус «Не размечено» не означает подтверждение. Проверьте роль памяти, '
        'значение, единицы и цитату. Исправьте поля или отметьте неоднозначность. '
        'Сохраните JSON перед закрытием. Это development-аудит, не независимый test.</p>\n'
    ) + text[end:]
    text = text.replace('no_predictions_or_ai', 'candidate_checked').replace('worked_independently', 'exposure_disclosed')
    text = text.replace('Для этих карточек не использовал(а) ИИ, интернет или predictions.',
                        'Проверил(а) значение, роль памяти, единицу и цитату по исходному тексту.')
    text = text.replace('Работал(а) независимо, не смотрел(а) ответы другого разметчика.',
                        'Понимаю: вижу предложение правил, результат не является слепым test.')
    text = text.replace("a.value)", "a.value??t.proposal.value)")
    text = text.replace("a.evidence?.field??'title'", "a.evidence?.field??t.proposal.evidence.field")
    text = text.replace("a.evidence?.text)", "a.evidence?.text??t.proposal.evidence.text)")
    text = text.replace("a.evidence?.start,'number'", "a.evidence?.start??t.proposal.evidence.start,'number'")
    return text.replace('__PAYLOAD__', json.dumps(payload, ensure_ascii=True).replace('<', '\\u003c'))


def materialize_review(output, selected, products):
    tasks = []
    for row in selected:
        a, p = row['candidate'], products[row['sku_id']]
        tasks.append({'task_id': row['task_id'], 'category_id': p.category_id,
                      'title': p.title, 'description': p.description,
                      'proposal': {'value': a['value'], 'unit': 'GB', 'evidence': a['evidence']},
                      'attributes': [{'attribute': 'storage_gb', 'status': 'unreviewed',
                                      'value': None, 'unit': None, 'evidence': None, 'notes': ''}]})
    package_id = hashlib.sha256(json.dumps(selected, sort_keys=True, ensure_ascii=True).encode()).hexdigest()
    payload = {'package_id': package_id, 'slot': 'storage-shadow', 'reviewer_id': 'Vladislav',
               'units': {'storage_gb': 'GB'}, 'tasks': tasks}
    dump(output/'tasks.private.json', payload)
    html = review_html(payload) if tasks else '<!doctype html><meta charset="utf-8"><p>Нет подходящих непросмотренных семейств.</p>'
    (output/'review.html').write_text(html, encoding='utf-8')
    for offset in range(0, len(tasks), POLICY['batch_size']):
        subset = tasks[offset:offset+POLICY['batch_size']]
        lines = ['# Проверка storage_gb: предложения правил', '',
                 'Это не AI-разметка и не независимый test. Каталожные ответы скрыты.',
                 'Проверьте все случаи. Ответ: `S001–S050: подтверждаю после проверки`, '
                 'либо перечислите ошибки/сомнения. Непросмотренные случаи не подтверждаются.', '']
        for t in subset:
            a = t['proposal']
            lines += [f"## {t['task_id']}", 'Заголовок:', fence(t['title']),
                      'Описание:', fence(t['description'] or '[нет описания]'),
                      f"Предложение правил: **{a['value']} GB** (накопитель).",
                      'Цитата:', fence(a['evidence']['text']),
                      f"Поле: {a['evidence']['field']}, offsets [{a['evidence']['start']}:{a['evidence']['end']}].", '']
        (output/f"review-{offset+1:03}-{offset+len(subset):03}.md").write_text('\n'.join(lines), encoding='utf-8')


def prepare(bundle, output, seen_paths=()):
    bundle = Path(bundle).resolve()
    source_manifest = verify_bundle(bundle)
    config = load_config()
    require(json.loads((bundle/'policy.json').read_text(encoding='utf-8'))['config'] == config,
            'bundle_config_mismatch')
    require(source_manifest.get('protected_text_exported') is False, 'protected_population_not_excluded')
    seen_paths = [Path(p).resolve() for p in seen_paths]
    source_paths = [bundle/'manifest.json', bundle/'input.jsonl', bundle/'reference.jsonl',
                    bundle/'metadata.jsonl', bundle/'policy.json', *seen_paths]
    output = Path(output).resolve()
    require(output != bundle and bundle not in output.parents, 'output_inside_source_bundle')
    output = new_directory(output)
    freeze = {'policy': POLICY, 'source_hashes': {str(p): digest(p) for p in source_paths},
              'tool_hashes': tool_hashes(), 'runtime': identity(config),
              'reference_kind': 'catalog_silver', 'independent_reference': False}
    dump(output/'freeze.json', freeze)  # Before metadata, input, reference or predictions are parsed.
    metadata = unique(read_jsonl(bundle/'metadata.jsonl'))
    roles_by_family = defaultdict(set)
    for m in metadata.values():
        require(m.get('original_split') in {'development', 'validation'} and m.get('role') in ROLES,
                'protected_or_unknown_split')
        require(isinstance(m.get('family_id'), str) and m['family_id'], 'missing_family')
        roles_by_family[m['family_id']].add(m['role'])
    require(all(len(v) == 1 for v in roles_by_family.values()), 'cross_role_family')
    inputs = unique(read_jsonl(bundle/'input.jsonl'))
    require(inputs.keys() == metadata.keys(), 'input_metadata_mismatch')
    products = {s: Product.from_dict(row) for s,row in inputs.items()}
    require(all(p.category_id == metadata[s]['category_id'] for s,p in products.items()), 'category_mismatch')
    seen = set().union(*(exposure_ids(p) for p in seen_paths)) if seen_paths else set()
    cold = predict(bundle/'input.jsonl', output/'predictions.jsonl', config)
    warm = predict(bundle/'input.jsonl', output/'repeat.jsonl', config)
    require(digest(output/'predictions.jsonl') == digest(output/'repeat.jsonl'), 'non_deterministic_predictions')
    predictions = unique(read_predictions(output/'predictions.jsonl'))
    candidates, reasons = [], Counter()
    for s, product in products.items():
        reason = select_reason(product, predictions[s], config)
        reasons[reason or 'shadow_selected'] += 1
        if reason is None:
            candidate = next(a for a in predictions[s]['attributes'] if a['attribute'] == 'storage_gb')
            candidates.append({'sku_id': s, 'candidate': candidate})
    selected, available_families, blocked_families = family_sample(candidates, metadata, seen)
    write_rows(output/'selection.private.jsonl', selected)  # Before reference is read.
    materialize_review(output, selected, products)
    references = unique(read_jsonl(bundle/'reference.jsonl'))
    require(references.keys() == inputs.keys(), 'reference_population_mismatch')
    report, pairs, _ = evaluate_rows(inputs.values(), references.values(), metadata.values(),
                                   predictions.values(), config, repeats=1000)
    calibration, _ = calibrate(pairs)
    dump(output/'silver.calibration.json', calibration)
    write_rows(output/'pair_diagnostics.private.jsonl', pairs)
    catalog_counts = Counter()
    slices = defaultdict(Counter)
    for row in candidates:
        s, a = row['sku_id'], row['candidate']
        label = next(x for x in references[s]['attributes'] if x['attribute'] == 'storage_gb')
        correct = label['status'] == 'known' and (a['value'], a['unit']) == (label['value'], label['unit'])
        counts = {'selected': 1, 'tp': int(correct), 'fp': int(label['status'] == 'known' and not correct),
                  'unknown': int(label['status'] == 'unknown'), 'conflict': int(label['status'] == 'conflict')}
        catalog_counts.update(counts)
        for key in [a['rule_id'], 'field:'+a['evidence']['field'], 'role:'+metadata[s]['role']]:
            slices[key].update(counts)
    phones = sum(p.category_id == '761' for p in products.values())
    filled_storage = sum(a['decision'] == 'review' and a['attribute'] == 'storage_gb'
                         for p in predictions.values() if p['category_id'] == '761' for a in p['attributes'])
    curve = []
    for threshold in POLICY['raw_score_diagnostics']:
        rows = [p for p in pairs if p['category_id'] == '761' and p['attribute'] == 'storage_gb'
                and p['heuristic_score'] is not None and p['heuristic_score'] >= threshold]
        known = [p for p in rows if p['correct'] is not None]
        curve.append({'raw_score_min': threshold, 'selected': len(rows), 'assessed': len(known),
                      'precision_catalog': fraction(sum(p['correct'] for p in known), len(known)),
                      'coverage_phone_storage': fraction(len(rows), phones)})
    shadow_n = len(candidates)
    result = {'policy_version': POLICY['version'], 'runtime_auto_accept': False,
              'independent_reference': False, 'human_precision': None, 'human_precision_lower_95': None,
              'human_status': 'pending' if selected else 'no_unexposed_eligible_families',
              'runtime_enablement': 'blocked_independent_calibration_and_contract_approval',
              'requested_all_fields': report['agreement']['requested'],
              'phone_cards': phones, 'found_storage': filled_storage, 'shadow_selected_storage': shadow_n,
              'shadow_coverage_phone_storage': fraction(shadow_n, phones),
              'share_found_storage_selected': fraction(shadow_n, filled_storage),
              'remaining_storage_review': filled_storage-shadow_n,
              'remaining_all_fields_review': report['agreement']['predicted']-shadow_n,
              'actual_runtime_review': report['agreement']['predicted'],
              'actual_runtime_abstain': report['agreement']['abstain'],
              'catalog_selected': dict(catalog_counts),
              'catalog_selected_precision': fraction(catalog_counts['tp'],catalog_counts['tp']+catalog_counts['fp']),
              'diagnostic_slices': dict(slices), 'raw_score_curve_catalog_only': curve,
              'policy_exclusions': dict(reasons), 'audit_cards': len(selected),
              'audit_eligible_unexposed_families': available_families,
              'exposure_blocked_families': blocked_families,
              'audit_estimand': 'one_candidate_per_uniformly_sampled_family_not_sku_weighted',
              'reference_kind': 'catalog_silver', 'test_reserved_opened': False,
              'llm_calls': 0, 'model_api_cost_rub': 0,
              'resources': {'cold_cards_per_second': cold['cards_per_second_including_io'],
                            'warm_cards_per_second': warm['cards_per_second_including_io']},
              'repeat_predictions_identical': True}
    sources_unchanged(freeze)
    dump(output/'diagnostics.json', result)
    (output/'summary.md').write_text(
        '# Storage shadow: предварительные измерения\n\n'
        f"Смартфоны: {phones}. Найдено storage: {filled_storage}. Shadow-selected: {shadow_n}.\n\n"
        f"Каталоговый reference: {dict(catalog_counts)}. Это не human precision.\n\n"
        f"Для человека: {len(selected)} случаев, одна карточка на семью, без известных exposures.\n\n"
        'Откройте review.html или первую партию review-001-050.md. '
        'Предложения правил не являются подтверждёнными метками. Human precision=N/A до ответа.\n\n'
        'Runtime по-прежнему review/abstain. Независимые gates #6/#38/#39 не закрыты.\n', encoding='utf-8')
    seal(output, 'storage-shadow')
    return result


def assess(bundle, answers_path, output):
    bundle = Path(bundle).resolve()
    checked(bundle, 'storage-shadow')
    freeze = json.loads((bundle/'freeze.json').read_text(encoding='utf-8'))
    sources_unchanged(freeze)
    payload = json.loads((bundle/'tasks.private.json').read_text(encoding='utf-8'))
    response = json.loads(Path(answers_path).read_text(encoding='utf-8'))
    require(isinstance(response, dict), 'answer_object_required')
    require(set(response) == {'package_id', 'slot', 'reviewer_id', 'attestation', 'tasks'}, 'answer_fields')
    require(all(response.get(k) == payload[k] for k in ['package_id', 'slot', 'reviewer_id']), 'answer_identity')
    require(isinstance(response['attestation'], dict)
            and set(response['attestation']) == {'human_only', 'candidate_checked', 'exposure_disclosed'}
            and all(v is True for v in response['attestation'].values()),
            'human_attestation_required')
    proposed = {t['task_id']: t for t in payload['tasks']}
    require(isinstance(response['tasks'], list), 'answer_tasks_required')
    observed, counts = {}, Counter(correct=0, incorrect=0, unresolved=0, pending=0)
    judged = []
    for row in response['tasks']:
        tid = row.get('task_id')
        require(tid in proposed and tid not in observed, 'answer_task_identity')
        require(set(row) == {'task_id', 'attributes'} and isinstance(row['attributes'], list)
                and len(row['attributes']) == 1, 'answer_task_fields')
        label, task = row['attributes'][0], proposed[tid]
        require(isinstance(label, dict) and set(label) == {'attribute', 'status', 'value', 'unit', 'evidence', 'notes'}
                and label['attribute'] == 'storage_gb' and isinstance(label['notes'], str), 'answer_label_fields')
        status = label['status']
        require(status in {'present', 'absent', 'ambiguous', 'unjudgeable', 'unreviewed'}, 'answer_status')
        if status == 'present':
            require(isinstance(label['value'], str) and label['unit'] == 'GB'
                    and numeric('storage_gb', label['value'], label['unit']) == label['value'], 'answer_value_unit')
            label = label | {'evidence': evidence(label, task)}
            correct = label['value'] == task['proposal']['value']
            outcome = 'correct' if correct else 'incorrect'
        else:
            require(all(label[k] is None for k in ['value', 'unit', 'evidence']), 'nonpresent_fields_not_empty')
            require(status not in {'ambiguous', 'unjudgeable'} or bool(label['notes'].strip()), 'uncertainty_reason_required')
            outcome = 'pending' if status == 'unreviewed' else 'incorrect' if status == 'absent' else 'unresolved'
        observed[tid] = label
        counts[outcome] += 1
        judged.append({'task_id': tid, 'outcome': outcome, 'label': label})
    require(observed.keys() == proposed.keys(), 'incomplete_task_set')
    total = len(proposed)
    complete = total > 0 and counts['pending'] == 0
    lower = precision_lower(counts['correct'], total) if complete else None
    report = {'policy_version': POLICY['version'], 'counts': dict(counts), 'sample_size': total,
              'review_complete': complete, 'human_precision_family_sample': fraction(counts['correct'], total) if complete else None,
              'conservative_one_sided_lower_95': lower,
              'numerical_target_met': lower is not None and lower >= POLICY['target_precision'],
              'independent_reference': False, 'runtime_auto_accept': False,
              'enablement': 'blocked_independent_calibration_and_contract_approval',
              'limitations': ['Human sees a deterministic proposal; developer review is not blind gold.',
                              'Family-balanced selected sample is not production SKU-weighted precision.',
                              'Binomial bound assumes independent representative family observations.',
                              'Unresolved judgments count as errors for the conservative lower bound.'],
              'answers_sha256': digest(Path(answers_path)), 'bundle_manifest_sha256': digest(bundle/'manifest.json')}
    output = new_directory(output)
    dump(output/'human.metrics.json', report)
    write_rows(output/'human.judgments.private.jsonl', judged)
    seal(output, 'storage-shadow-reviewed')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('--bundle', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--seen', action='append', type=Path, default=[])
    p = sub.add_parser('assess')
    p.add_argument('--bundle', type=Path, required=True)
    p.add_argument('--answers', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.bundle, args.output_dir, args.seen) if args.command == 'prepare' else assess(args.bundle, args.answers, args.output_dir)
    print(json.dumps(result, ensure_ascii=True, allow_nan=False, indent=2))


if __name__ == '__main__':
    main()
