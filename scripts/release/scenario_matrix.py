"""SPEC-002 executable evidence gate. Passing is not complete case coverage or quality."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.release import external_acceptance
from scripts.release.clean_run import destination, sha, verify_pair
from scripts.release.external_cases import generated_cases, ATTRIBUTES
from scripts.release.scenario_cases import policy_cases
from scripts.release.scenario_catalog import VERSION, REQUIREMENTS, SCENARIOS, SUITES, EVIDENCE_TESTS
from goodsai.config import load_config
from goodsai.data import write_json
from goodsai.runtime import identity

REQUIRED_IDS = frozenset(REQUIREMENTS)
STAGES = frozenset({'isolated_package_without_examples', 'external_cli', 'prediction_manifest',
    'malformed_jsonl_preserves_pair', 'http_invalid_json', 'http_wrong_media', 'http_body_limit',
    'http_recovery_after_errors', 'server_cleanup', 'all_external_checks'})
STATES = {'implemented', 'not_implemented', 'not_verified', 'unknown'}
SOURCE_KINDS = {'case_requirement', 'team_policy', 'unknown_condition'}
ALLOWED_INPUTS = ['schema_version', 'sku_id', 'category_id', 'title', 'description',
                  'seller_attributes (empty in E1)', 'source_flags (provenance only)']
FORBIDDEN_HINTS = ['catalog vendor/model/params', 'gold/target', 'clicks', 'SKU lookup', 'images']


def oracle(seed):
    legacy = json.loads((ROOT / 'src/goodsai/examples/synthetic/adversarial.json').read_text(encoding='utf-8'))
    return generated_cases(seed) + [dict(c, id='qa-001/' + c['id']) for c in legacy['cases']] + policy_cases(seed)


def validate_catalog(requirements, scenarios, cases, config):
    if not REQUIRED_IDS <= requirements.keys() or not scenarios:
        raise ValueError('Required inventory entry missing')
    by_case = {c['id']: c for c in cases}
    if len(by_case) != len(cases):
        raise ValueError('Duplicate oracle ID')
    for case in cases:
        expected = case['expected']
        attrs = expected['attributes']
        if (case['id'].startswith(('generated/', 'matrix/')) and expected['status'] == 'processed'
                and set(attrs) != set(config['categories'].get(case['input']['category_id'], []))):
            raise ValueError('Fresh oracle must specify every category attribute')
        for wanted in attrs.values():
            if not {'value', 'unit', 'decision', 'evidence'} <= wanted.keys():
                raise ValueError('Oracle must assert value, unit, decision and evidence')
            evidence = wanted['evidence']
            if evidence:
                source = case['input'][evidence['field']]
                if source[evidence['start']:evidence['end']] != evidence['text']:
                    raise ValueError('Oracle evidence is not an exact source slice')
    membership = Counter(s for r in requirements.values() for s in r['scenarios'])
    if set(membership) != set(scenarios) or any(n != 1 for n in membership.values()):
        raise ValueError('Missing, duplicate or orphan scenario binding')
    covered_attributes = {c: set() for c in config['categories']}
    for rid, req in requirements.items():
        if (not re.fullmatch(r'REQ-\d{3}', rid) or not req['scenarios']
                or req['source_kind'] not in SOURCE_KINDS or type(req['executable_required']) is not bool):
            raise ValueError('Invalid requirement metadata')
        reference = PurePosixPath(req['reference'])
        if reference.is_absolute() or '..' in reference.parts or not (ROOT / reference).is_file():
            raise ValueError('Missing requirement source')
        source_text = (ROOT / reference).read_text(encoding='utf-8')
        locators = re.findall(r'P\d{2}', req['section']) or [req['section']]
        if not all(locator and locator in source_text for locator in locators):
            raise ValueError('Requirement section no longer exists in its source')
        for sid in req['scenarios']:
            scenario = scenarios[sid]
            if (not re.fullmatch(r'SCN-\d{3}', sid) or scenario['state'] not in STATES
                    or scenario['kind'] not in {'positive', 'negative', 'boundary', 'gap'}):
                raise ValueError('Invalid scenario metadata')
            implemented = scenario['state'] == 'implemented'
            if implemented != req['executable_required'] or (scenario['state'] == 'unknown') != (req['source_kind'] == 'unknown_condition'):
                raise ValueError('Required evidence cannot be downgraded to a gap or unknown')
            if not implemented:
                if scenario['evidence'] or not scenario.get('reason') or not scenario['issues']:
                    raise ValueError('Gaps require an explicit reason and issue, without passing evidence')
                continue
            if not scenario['evidence']:
                raise ValueError('Implemented requirement has no executable evidence')
            seen = set()
            for ref in scenario['evidence']:
                key = (ref['kind'], ref['key'])
                if key in seen:
                    raise ValueError('Duplicate evidence binding')
                seen.add(key)
                if ref['kind'] == 'case':
                    if ref['key'] not in by_case:
                        raise ValueError('Unknown oracle case')
                    case = by_case[ref['key']]
                    for attr, wanted in case['expected']['attributes'].items():
                        category = case['input']['category_id']
                        if wanted.get('value') is not None and category in covered_attributes:
                            covered_attributes[category].add(attr)
                elif ref['kind'] == 'stage':
                    if ref['key'] not in STAGES:
                        raise ValueError('Unknown external stage')
                elif ref['kind'] == 'suite':
                    if ref['key'] not in SUITES or not (ROOT / SUITES[ref['key']]).is_file():
                        raise ValueError('Missing offline test suite')
                else:
                    raise ValueError('Unknown evidence driver')
    if any(set(attrs) - covered_attributes[category] for category, attrs in config['categories'].items()):
        raise ValueError('A supported category attribute has no positive scenario')
    return by_case


def evaluate(requirements, scenarios, external, suites, expected_cases):
    """A missing/duplicate check is a failure, never an implicit skip or pass."""
    rows = []
    for rid, req in requirements.items():
        for sid in req['scenarios']:
            spec = scenarios[sid]
            row = dict(id=sid, requirement_id=rid, title=spec['title'], kind=spec['kind'],
                       source_kind=req['source_kind'], source=req['reference'], source_section=req['section'],
                       current_e1_allowed_inputs=ALLOWED_INPUTS, forbidden_hints=FORBIDDEN_HINTS,
                       issues=spec['issues'], evidence=[], status=spec['state'], reason=spec.get('reason'))
            if spec['state'] == 'implemented':
                for ref in spec['evidence']:
                    if ref['kind'] == 'case':
                        for transport in ('cli', 'http'):
                            matches = [x for x in external.get('cases', [])
                                       if x['id'] == ref['key'] and x['transport'] == transport]
                            row['evidence'].append(dict(**ref, transport=transport,
                                passed=len(matches) == 1 and matches[0].get('passed') is True,
                                artifacts=['external/expected.json', 'external/input.jsonl',
                                    'external/report.json', 'external/predictions.jsonl' if transport == 'cli'
                                    else 'external/http_predictions.json']))
                    elif ref['kind'] == 'stage':
                        if ref['key'] == 'all_external_checks':
                            checks, stages = external.get('cases', []), external.get('stages', [])
                            expected_keys = {(c['id'], t) for c in expected_cases for t in ('cli', 'http')}
                            stage_keys = STAGES - {'all_external_checks'}
                            total = len(expected_keys) + len(stage_keys)
                            passed = (external.get('status') == 'passed' and bool(expected_keys)
                                and len(checks) == len(expected_keys)
                                and {(c['id'], c['transport']) for c in checks} == expected_keys
                                and len(stages) == len(stage_keys) and {s['name'] for s in stages} == stage_keys
                                and all(c.get('passed') is True for c in checks + stages)
                                and external.get('checks_passed') == external.get('checks_total') == total)
                        else:
                            matches = [x for x in external.get('stages', []) if x['name'] == ref['key']]
                            passed = len(matches) == 1 and matches[0].get('passed') is True
                        row['evidence'].append(dict(**ref, passed=passed, artifacts=['external/report.json']))
                    else:
                        row['evidence'].append(dict(**ref, passed=suites.get(ref['key'], {}).get('passed') is True,
                            test_file=SUITES[ref['key']], artifacts=[f"offline-{ref['key']}.json"]))
                row['status'] = 'passed' if row['evidence'] and all(e['passed'] for e in row['evidence']) else 'failed'
            rows.append(row)
    return rows


def offline_suite(name, output, env):
    # A child process reports counts, not arbitrary test logs, product text or credentials.
    if name == 'demo':
        code = ("import json; from pathlib import Path; from goodsai.demo import run_demo,verify_demo_kit; "
                "import sys; r=run_demo(Path(sys.argv[1])); verify_demo_kit(Path(sys.argv[1])); "
                "print(json.dumps({'passed':r['checks_passed']==r['checks_total'] and r['checks_total']>0,"
                "'checks_run':r['checks_total']}))")
        args = [sys.executable, '-c', code, str(output / 'packaged-demo')]
    else:
        code = ("import io,json,sys,unittest\n"
                "def ids(s):\n"
                " return [i for t in s for i in ids(t)] if isinstance(s,unittest.TestSuite) else [s.id()]\n"
                "s=unittest.defaultTestLoader.discover('tests',pattern=sys.argv[1]); names=ids(s); "
                "r=unittest.TextTestRunner(stream=io.StringIO()).run(s); "
                "print(json.dumps({'passed':r.wasSuccessful() and r.testsRun>0 and not r.skipped,"
                "'test_ids':names,'checks_run':r.testsRun,'skipped':len(r.skipped),'failures':len(r.failures),'errors':len(r.errors)}))")
        args = [sys.executable, '-c', code, Path(SUITES[name]).name]
    result = subprocess.run(args, cwd=ROOT, env=env, timeout=120, capture_output=True)
    try:
        report = json.loads(result.stdout) if result.returncode == 0 else dict(passed=False, exit_code=result.returncode)
    except (ValueError, UnicodeError):
        report = dict(passed=False, error_kind='InvalidSuiteReport')
    if not isinstance(report, dict):
        report = dict(passed=False, error_kind='InvalidSuiteReport')
    if type(report.get('checks_run')) is not int or report['checks_run'] <= 0:
        report['passed'] = False
    if name != 'demo':
        names = report.get('test_ids')
        valid = (isinstance(names, list) and all(isinstance(n, str) for n in names)
                 and len(names) == len(set(names)) == report.get('checks_run'))
        missing = sorted(EVIDENCE_TESTS.get(name, set()) - set(names if valid else []))
        report['required_tests_missing'] = missing
        if not valid or missing:
            report['passed'] = False
    report.update(driver=SUITES[name], driver_sha256=sha(ROOT / SUITES[name]), provider='fake_or_disabled', live_calls=0)
    write_json(output / f'offline-{name}.json', report)
    return report


def render(report):
    lines = ['# GoodsAI scenario matrix', '', f"Executable gate: **{report['status']}**.",
        f"Source: `{report['identity']['git_commit']}`; dirty: `{report['identity']['git_dirty']}`.",
        f"Complete case evidence: **{report['complete_case_evidence']}**.",
        f"Scenario outcomes (all tracked): `{json.dumps(report['counts'], sort_keys=True)}`.",
        'Synthetic contract evidence only. Catalogue precision/recall/F1: N/A; live LLM calls: 0.',
        'Packaged smoke and external runtime without examples are separate evidence paths.', '',
        '| ID | Source status | Scenario | Outcome | Evidence / open issue |',
        '| --- | --- | --- | --- | --- |']
    for row in report['scenarios']:
        refs = ', '.join(sorted({f"[{e['key']}]({e['artifacts'][0]})" for e in row['evidence']})) or row['reason']
        issues = ', '.join(f"[#{n}](https://github.com/CRUDoshleps/GoodsAI/issues/{n})" for n in row['issues'])
        source = f"https://github.com/CRUDoshleps/GoodsAI/blob/{report['identity']['git_commit']}/{row['source']}"
        lines.append(f"| {row['id']} | [{row['source_kind']}]({source}) | {row['title']} | {row['status']} | {refs} {issues} |")
    lines += ['', 'A green executable gate does not close the gaps above or certify all categories,',
              'a human reference, a calibrated threshold, production deployment or final delivery.',
              'Source/output hashes and per-scenario artifact bindings: `scenario.manifest.json`.']
    return '\n'.join(lines) + '\n'


def run(output, seed, *, requirements=None, scenarios=None):
    output = destination(output)
    output.mkdir(parents=True, exist_ok=False)
    requirements = REQUIREMENTS if requirements is None else requirements
    scenarios = SCENARIOS if scenarios is None else scenarios
    config = load_config()
    report = dict(version=VERSION, policy='spec-team-v1', seed=seed, status='error',
                  complete_case_evidence=False, identity=identity(config), counts={}, scenarios=[],
                  quality='N/A_synthetic_not_catalog_quality', live_llm_calls=0)
    catalog_valid, external, suites = False, {}, {}
    try:
        cases = oracle(seed)
        validate_catalog(requirements, scenarios, cases, config)
        catalog_valid = True
        write_json(output / 'catalog.json', dict(requirements=requirements, scenarios=scenarios))
        external = external_acceptance.run(output / 'external', seed, additional_cases=policy_cases(seed))
        env = {k: v for k, v in os.environ.items() if not k.startswith(('GOODSAI_', 'OPENAI_', 'PYTHON'))}
        env.update(PYTHONUTF8='1', PYTHONNOUSERSITE='1')
        suites = {name: offline_suite(name, output, env) for name in SUITES}
        report['scenarios'] = evaluate(requirements, scenarios, external, suites, cases)
        report['counts'] = dict(Counter(row['status'] for row in report['scenarios']))
        report['status'] = 'failed' if report['counts'].get('failed', 0) else 'passed'
        report['complete_case_evidence'] = all(row['status'] == 'passed' for row in report['scenarios'])
        report['executable_gate'] = dict(passed=report['counts'].get('passed', 0),
                                        required=sum(s['state'] == 'implemented' for s in scenarios.values()))
        report['external_checks'] = dict(passed=external['checks_passed'], total=external['checks_total'])
        bound_cases = {e['key'] for s in scenarios.values() for e in s['evidence'] if e['kind'] == 'case'}
        report['positive_attribute_evidence'] = {
            category: {attr: sorted(c['id'] for c in cases if c['id'] in bound_cases
                and c['input']['category_id'] == category
                and c['expected']['attributes'].get(attr, {}).get('value') is not None)
                for attr in attrs} for category, attrs in config['categories'].items()}
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        report.update(status='error', error_kind=type(exc).__name__, exception_details_suppressed=True)
        if catalog_valid:
            report['scenarios'] = evaluate(requirements, scenarios, external, suites, cases)
            report['counts'] = dict(Counter(row['status'] for row in report['scenarios']))
    write_json(output / 'report.json', report)
    (output / 'report.md').write_text(render(report), encoding='utf-8', newline='\n')
    sources = [Path(__file__), ROOT / 'scripts/release/scenario_catalog.py', ROOT / 'scripts/release/scenario_cases.py',
               ROOT / 'scripts/release/external_cases.py', ROOT / 'scripts/release/external_acceptance.py',
               ROOT / 'src/goodsai/baseline.json'] + [ROOT / r['reference'] for r in requirements.values()] + [ROOT / p for p in SUITES.values()]
    manifest = dict(version=VERSION, source=report['identity'], policy='spec-team-v1', seed=seed,
        sources={p.relative_to(ROOT).as_posix(): sha(p) for p in set(sources) if p.is_file()},
        scenarios=[dict(id=r['id'], status=r['status'], artifacts=sorted({a for e in r['evidence'] for a in e['artifacts']}),
                        release_artifacts=['code', 'pipeline', 'predictions'] if r['evidence'] else []) for r in report['scenarios']],
        final_six_artifact_delivery=False,
        files={p.relative_to(output).as_posix(): dict(sha256=sha(p), bytes=p.stat().st_size)
               for p in sorted(output.rglob('*')) if p.is_file() and not p.name.endswith('.lock')})
    write_json(output / 'scenario.manifest.json', manifest)
    return report


def verify(output):
    output = destination(output)
    manifest = json.loads((output / 'scenario.manifest.json').read_text(encoding='utf-8'))
    if manifest.get('version') != VERSION or not manifest.get('files'):
        raise ValueError('Invalid matrix manifest')
    for name, record in manifest['files'].items():
        path = output / name
        if path.resolve() != path or output not in path.parents or not path.is_file():
            raise ValueError('Unsafe or missing matrix artifact')
        if sha(path) != record['sha256'] or path.stat().st_size != record['bytes']:
            raise ValueError('Matrix artifact hash mismatch')
    report = json.loads((output / 'report.json').read_text(encoding='utf-8'))
    if report['status'] != 'passed':
        raise ValueError('Failed or incomplete execution is not verified')
    for row in manifest['scenarios']:
        if any(name not in manifest['files'] for name in row['artifacts']):
            raise ValueError('Missing scenario artifact binding')
    if {p.relative_to(output).as_posix() for p in output.rglob('*')
            if p.is_file() and not p.name.endswith('.lock') and p.name != 'scenario.manifest.json'} != set(manifest['files']):
        raise ValueError('Matrix file inventory differs from manifest')
    verify_pair(output / 'external')
    return dict(status='verified', files=len(manifest['files']), complete_case_evidence=report['complete_case_evidence'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--output-dir', type=Path)
    group.add_argument('--verify', type=Path)
    parser.add_argument('--seed', type=int, default=20261020)
    args = parser.parse_args(argv)
    try:
        report = verify(args.verify) if args.verify else run(args.output_dir, args.seed)
        if report['status'] == 'passed':
            verify(args.output_dir)
        print(json.dumps({k: report[k] for k in ('status', 'counts', 'executable_gate', 'complete_case_evidence') if k in report}))
        return {'passed': 0, 'verified': 0, 'failed': 1, 'error': 2}[report['status']]
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps(dict(status='error', error_kind=type(exc).__name__)), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
