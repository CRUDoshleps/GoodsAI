"""QA-001 synthetic expected-output probes through the real batch pipeline.

Exit 1 means observed regressions, including known issues. No xfail suppression.
Exit 2 means a failed run. A passing suite is not catalogue accuracy.
"""
import argparse
import hashlib
from importlib.resources import files
import json
from pathlib import Path
import sys

from goodsai.cli import predict
from goodsai.contracts import Product, load_config, validate_prediction
from goodsai.data import read_predictions, write_json
from goodsai.demo import _destination


def run_suite(output_dir):
    examples = files('goodsai').joinpath('examples','synthetic')
    raw = examples.joinpath('adversarial.json').read_bytes()
    fixture = json.loads(raw)
    cases = fixture['cases']
    if len({c['id'] for c in cases}) != len(cases):
        raise ValueError('Duplicate synthetic case IDs')
    output = _destination(Path(output_dir),examples)
    output.mkdir(parents=True,exist_ok=False)
    source=output/'input.jsonl'
    source.write_text(''.join(json.dumps(c['input'],ensure_ascii=False)+'\n' for c in cases),encoding='utf-8')
    config=load_config()
    report={'suite':fixture['version'],'scope':fixture['origin'],
            'fixture_sha256':hashlib.sha256(raw).hexdigest(), 'quality':'N/A_synthetic_not_human_gold',
            'status':'running','cases':[], 'provider_route':'N/A_disabled_rules_only'}
    try:
        identity=predict(source,output/'predictions.jsonl',config)
        predictions=list(read_predictions(output/'predictions.jsonl'))
        if len(predictions)!=len(cases):raise ValueError('Case count mismatch')
        for case,row in zip(cases,predictions):
            errors=[];expected=case['expected']
            if row['sku_id']!=case['input']['sku_id'] or row['status']!=expected['status']:
                errors.append('identity_or_status')
            if expected['status']=='invalid_input':
                validate_prediction(row,config)
                if row.get('reason_codes')!=['invalid_text_only_input']:errors.append('invalid_input_reason')
            else:
                validate_prediction(row,config,Product.from_dict(case['input']))
            attrs={a['attribute']:a for a in row['attributes']}
            for attr,wanted in expected['attributes'].items():
                actual=attrs.get(attr)
                for key,value in wanted.items():
                    if actual is None or actual.get(key)!=value:errors.append(attr+'.'+key)
            report['cases'].append({'id':case['id'],'passed':not errors,'mismatched_fields':errors,
                                    'known_issue':case.get('known_issue')})
        report.update(status='passed' if all(c['passed'] for c in report['cases']) else 'failed',
                      checks_passed=sum(c['passed'] for c in report['cases']),checks_total=len(cases),
                      identity={k:identity[k] for k in ['run_id','code_sha256','config_sha256','git_commit','git_dirty']})
    except (ValueError,OSError,RuntimeError,KeyError,TypeError) as exc:
        report.update(status='error',error_kind=type(exc).__name__,exception_details_suppressed=True)
    write_json(output/'report.json',report)
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args(argv)
    try:result=run_suite(args.output_dir)
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print(json.dumps({'status':'error','error_kind':type(exc).__name__}),file=sys.stderr)
        return 2
    print(json.dumps(result,ensure_ascii=True,indent=2))
    return {'passed':0,'failed':1,'error':2}[result['status']]


if __name__=='__main__':raise SystemExit(main())
