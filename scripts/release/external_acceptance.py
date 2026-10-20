"""QA-006 strict external CLI/socket acceptance. Synthetic only; exit 1 is a regression."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
# Also works as `python scripts/release/external_acceptance.py` from a checkout.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.release.clean_run import destination, sha, verify_pair
from scripts.release.external_cases import VERSION, generated_cases
from scripts.release.probe_http import listening_server, request_json
from goodsai.adversarial import case_errors
from goodsai.contracts import load_config
from goodsai.data import read_predictions, write_json as save
from goodsai.runtime import identity


def command(args, cwd, env):
    return subprocess.run([str(x) for x in args], cwd=cwd, env=env, timeout=90,
                          capture_output=True, check=False)


def check(cases, rows, config):
    if len(rows) != len(cases):
        raise ValueError('Prediction count mismatch')
    return [{'id': c['id'], 'passed': not (errors := case_errors(c, row, config)),
             'mismatched_fields': errors, 'known_issue': c.get('known_issue')}
            for c, row in zip(cases, rows)]


def comparable(row):
    return {k: v for k, v in row.items() if k != 'run_id'}


def result_code(report):
    return {'passed': 0, 'failed': 1, 'error': 2}[report['status']]


def run(output, seed):
    output = destination(output)
    output.mkdir(parents=True, exist_ok=False)  # Never overwrite an earlier run.
    config = load_config()
    source_identity = identity(config)
    report = {'suite': VERSION, 'seed': seed, 'status': 'running', 'identity': source_identity,
              'quality': 'N/A_synthetic_not_catalog_quality', 'mode': 'rules', 'llm_calls': 0,
              'uncovered_requirements': ['independent catalogue quality', 'official organizer API',
                  'seller attributes beyond current E1', 'categories beyond 761/482',
                  'live model quality/failures', 'operator UI/persistence'], 'stages': [], 'cases': []}

    def stage(name, passed, **details):
        report['stages'].append(dict(name=name, passed=passed, **details))
        save(output / 'report.json', report)

    try:
        # Read legacy expected probes BEFORE isolation; only the harness can use them.
        legacy_path = ROOT / 'src/goodsai/examples/synthetic/adversarial.json'
        legacy = json.loads(legacy_path.read_text(encoding='utf-8'))
        fresh = generated_cases(seed)
        cases = fresh + [dict(c, id='qa-001/' + c['id']) for c in legacy['cases']]
        if len({c['id'] for c in cases}) != len(cases):
            raise ValueError('Duplicate case IDs')
        report.update(generated_cases=len(fresh), legacy_cases=len(legacy['cases']),
                      legacy_fixture_sha256=sha(legacy_path))
        save(output / 'expected.json', {'grammar': VERSION, 'seed': seed, 'cases': cases})
        input_path = output / 'input.jsonl'
        input_path.write_text(''.join(json.dumps(c['input'], ensure_ascii=False) + '\n' for c in cases),
                              encoding='utf-8', newline='\n')
        report.update(input_sha256=sha(input_path), expected_sha256=sha(output / 'expected.json'),
                      runner_sha256=sha(Path(__file__)), grammar_sha256=sha(Path(__file__).with_name('external_cases.py')))

        with tempfile.TemporaryDirectory(prefix='goodsai-qa006-') as folder:
            sandbox = Path(folder).resolve()
            package = sandbox / 'goodsai'
            shutil.copytree(ROOT / 'src/goodsai', package, ignore=shutil.ignore_patterns('examples', '__pycache__', '*.pyc'))
            env = {k: v for k, v in os.environ.items()
                   if not k.startswith(('GOODSAI_', 'OPENAI_', 'PYTHON'))}
            env.update(PYTHONPATH=str(sandbox), PYTHONUTF8='1', PYTHONNOUSERSITE='1')
            isolated = command([sys.executable, '-c',
                'import goodsai,json; from pathlib import Path; '
                'p=Path(goodsai.__file__).resolve().parent; '
                'print(json.dumps({"package":str(p),"examples_exist":(p/"examples").exists()}))'], sandbox, env)
            proof = json.loads(isolated.stdout) if isolated.returncode == 0 else {}
            independent = proof.get('package') == str(package) and proof.get('examples_exist') is False
            stage('isolated_package_without_examples', independent,
                  package_from_sandbox=independent, examples_available=proof.get('examples_exist'))
            if not independent:
                raise ValueError('Source import leaked into isolated runtime')

            predictions = output / 'predictions.jsonl'
            batch = command([sys.executable, '-m', 'goodsai.cli', 'predict', '--input', input_path,
                             '--output', predictions], sandbox, env)
            stage('external_cli', batch.returncode == 0, exit_code=batch.returncode)
            if batch.returncode:
                raise RuntimeError('CLI execution failed')
            verify_pair(output)  # Existing checksum, contract and raw-evidence checks.
            manifest = json.loads((output / 'predictions.manifest.json').read_text(encoding='utf-8'))
            stage('prediction_manifest', manifest['llm_calls'] == 0 and
                  all(manifest[k] == source_identity[k] for k in ('config_sha256', 'code_sha256')),
                  config_sha256=manifest['config_sha256'], code_sha256=manifest['code_sha256'])
            rows = list(read_predictions(predictions))
            cli_checks = check(cases, rows, config)
            report['cases'].extend(dict(c, transport='cli') for c in cli_checks)

            # Syntactically broken JSONL must reject the run without replacing its last good pair.
            before = (predictions.read_bytes(), predictions.with_suffix('.manifest.json').read_bytes())
            malformed = output / 'malformed.jsonl'
            malformed.write_text(json.dumps(fresh[0]['input']) + '\n{\n' + json.dumps(fresh[-1]['input']) + '\n',
                                 encoding='utf-8', newline='\n')
            bad = command([sys.executable, '-m', 'goodsai.cli', 'predict', '--input', malformed,
                           '--output', predictions], sandbox, env)
            preserved = before == (predictions.read_bytes(), predictions.with_suffix('.manifest.json').read_bytes())
            stage('malformed_jsonl_preserves_pair', bad.returncode == 2 and preserved,
                  exit_code=bad.returncode, pair_preserved=preserved)
            verify_pair(output)

            http_rows = []
            with listening_server(sys.executable, sandbox, env) as (base, process):
                for case, cli_row in zip(cases, rows):
                    body = json.dumps(case['input'], ensure_ascii=False).encode('utf-8')
                    status, row, _ = request_json(base, '/predict', body)
                    if case['expected']['status'] == 'invalid_input':
                        passed = status == 422 and row.get('error', {}).get('code') == 'invalid_product'
                        errors = [] if passed else ['invalid_product_response']
                    else:
                        errors = case_errors(case, row, config)
                        if status != 200:
                            errors.append('http_status')
                        if comparable(row) != comparable(cli_row):
                            errors.append('cli_http_parity')
                    http_rows.append({'id': case['id'], 'status': status, 'response': row})
                    report['cases'].append(dict(id=case['id'], transport='http', passed=not errors,
                                               mismatched_fields=errors, known_issue=case.get('known_issue')))
                for name, body, media, want, code in [
                    ('invalid_json', b'{', 'application/json', 400, 'invalid_json'),
                    ('wrong_media', b'{}', 'text/plain', 415, 'unsupported_media_type'),
                    ('body_limit', b' ' * (config['runtime']['api']['max_body_bytes'] + 1),
                     'application/json', 413, 'request_too_large'),
                ]:
                    status, response, _ = request_json(base, '/predict', body, media)
                    stage('http_' + name, status == want and response.get('error', {}).get('code') == code,
                          http_status=status)
                # Confirm the server still handles valid requests after malformed requests.
                status, response, _ = request_json(base, '/predict', json.dumps(fresh[-1]['input']).encode('utf-8'))
                stage('http_recovery_after_errors', status == 200 and not case_errors(fresh[-1], response, config))
            stage('server_cleanup', process.poll() is not None)
            save(output / 'http_predictions.json', {'responses': http_rows})

        report['status'] = 'passed' if all(c['passed'] for c in report['cases'] + report['stages']) else 'failed'
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        report.update(status='error', error_kind=type(exc).__name__, exception_details_suppressed=True)
    report['case_checks_passed'] = sum(c['passed'] for c in report['cases'])
    report['case_checks_total'] = len(report['cases'])
    report['checks_passed'] = sum(c['passed'] for c in report['cases'] + report['stages'])
    report['checks_total'] = len(report['cases']) + len(report['stages'])
    report['files'] = {p.name: sha(p) for p in output.iterdir() if p.is_file()
                       and p.name not in {'report.json', 'report.md'} and not p.name.endswith('.lock')}
    save(output / 'report.json', report)
    lines = ['# GoodsAI external acceptance', '', f"Status: **{report['status']}**; seed: {seed}.",
             f"Source: `{source_identity['git_commit']}`; dirty: `{source_identity['git_dirty']}`.",
             'Synthetic contract checks only. Catalogue P/R/F1: N/A. LLM calls: 0.', '',
             '| Transport | Case | Passed | Mismatched fields / issue |', '| --- | --- | --- | --- |']
    lines.extend(f"| {c['transport']} | {c['id']} | {c['passed']} | {','.join(c['mismatched_fields'])} / {c['known_issue']} |"
                 for c in report['cases'])
    lines.extend(['', 'Stages:'] + [f"- {s['name']}: {s['passed']}" for s in report['stages']])
    lines.extend(['', 'Uncovered: ' + '; '.join(report['uncovered_requirements'])])
    (output / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=20261020)
    args = parser.parse_args(argv)
    try:
        report = run(args.output_dir, args.seed)
    except (ValueError, OSError) as exc:
        print(json.dumps({'status': 'error', 'error_kind': type(exc).__name__}), file=sys.stderr)
        return 2
    print(json.dumps({k: report[k] for k in ('status', 'seed', 'checks_passed', 'checks_total')}))
    return result_code(report)


if __name__ == '__main__':
    raise SystemExit(main())
