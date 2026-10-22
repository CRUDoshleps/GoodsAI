"""Train a text-only advisory score on frozen catalog-silver development groups.

Catalog agreement is a proxy label, never independent human correctness.
"""
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import time

from goodsai.confidence import normalized, row_features
from goodsai.config import load_config
from goodsai.contracts import Product
from goodsai.evaluate import evaluate
from goodsai.data import digest, preparation_directory, read_jsonl, write_json, write_line
from goodsai.silver_evaluate import evaluate_rows
from goodsai.silver_calibration import fit_logistic, logit, sigmoid
from goodsai.text import visible_view
from goodsai.verify import Extractor
from scripts.research.compare_confidence import summary, require
from scripts.release.build_release import code_hash, config_hash

ROOT = Path(__file__).resolve().parents[2]
ROLES = {'fit', 'calibration', 'diagnostic'}


def indexed(rows):
    result = {}
    for row in rows:
        require(row['sku_id'] not in result, 'Duplicate SKU')
        result[row['sku_id']] = row
    return result


def prepare(bundle, output):
    manifest_path = bundle / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    require(manifest.get('reference_kind') == 'catalog_silver' and manifest.get('protected_text_exported') is False,
            'Only the protected frozen development silver bundle is allowed')
    paths = [bundle / n for n in ('input.jsonl', 'reference.jsonl', 'metadata.jsonl')]
    for path in paths:
        require(digest(path) == manifest['artifacts'][path.name], 'Frozen input hash mismatch')
    products, refs, metas = [indexed(read_jsonl(p)) for p in paths]
    require(products.keys() == refs.keys() == metas.keys(), 'Population mismatch')
    selected = {sku for sku, m in metas.items() if m['role'] in ROLES and m['original_split'] == 'development'}
    group_roles = defaultdict(set)
    text_groups = defaultdict(set)
    for sku in sorted(selected):
        m, p = metas[sku], products[sku]
        group_roles[m['family_id']].add(m['role'])
        text = '\n'.join(normalized(visible_view(p.get(f) or '')[0]) for f in ('title','description'))
        text_groups[hashlib.sha256(text.encode()).hexdigest()].add(m['family_id'])
    # A chain of exact duplicate families is one component. Exclude crossing
    # components rather than moving a convenient record into another split.
    parent = {g: g for g in group_roles}
    def find(g):
        while parent[g] != g:
            parent[g] = parent[parent[g]]; g = parent[g]
        return g
    for groups in text_groups.values():
        groups = sorted(groups)
        for g in groups[1:]:
            a,b = find(groups[0]),find(g);parent[max(a,b)] = min(a,b)
    components = defaultdict(set)
    for g, roles in group_roles.items(): components[find(g)].update(roles)
    excluded_groups = {g for g in group_roles if len(components[find(g)]) > 1}
    selected = sorted(sku for sku in selected if metas[sku]['family_id'] not in excluded_groups)
    config = load_config(); extractor = Extractor(config)
    pairs, predictions = [], []
    output.parent.mkdir(parents=True, exist_ok=True)
    with preparation_directory(output, manifest_path, *paths) as stage:
        write_json(stage/'freeze.json', {'protocol':'candidate-confidence-v2',
            'reference_kind':'catalog_silver','independent_reference':False,
            'inputs_sha256':{p.name:digest(p) for p in paths}, 'source_manifest_sha256':digest(manifest_path),
            'code_sha256':code_hash(ROOT), 'config_sha256':config_hash(config),
            'source_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'selected_skus':selected, 'excluded_crossing_families':sorted(excluded_groups),
            'roles':{sku:{'role':metas[sku]['role'],'group':find(metas[sku]['family_id'])} for sku in selected}})
        with (stage/'predictions.private.jsonl').open('w',encoding='utf-8') as stream:
            for sku in selected:
                p = Product.from_dict(products[sku]); row = extractor.predict(p)
                write_line(stream,row);predictions.append(row)
                grouped=defaultdict(list);gate=extractor.gate_factory.create(p)
                for candidate in extractor.rules.candidates(p):
                    if gate.reason(candidate) is None: grouped[candidate.attribute].append(candidate)
                vectors=row_features(p,row,grouped)
                labels={a['attribute']:a for a in refs[sku]['attributes']}
                for a in row['attributes']:
                    label=labels[a['attribute']]
                    if a['value'] is None or label['status']!='known': continue
                    pairs.append({'sku_id':sku,'group':find(metas[sku]['family_id']),'role':metas[sku]['role'],
                        'attribute':a['attribute'],'category':p.category_id,'rule_id':a['rule_id'],
                        'scope':p.category_id+':'+a['attribute']+':'+a['rule_id'],
                        'correct':(a['value'],a['unit'])==(label['value'],label['unit']),
                        'features':vectors[a['attribute']], 'fixed':a['confidence']})
        metrics,_,_=evaluate_rows([products[s] for s in selected],[refs[s] for s in selected],
                                  [metas[s] for s in selected], predictions, config, repeats=100)
        write_json(stage/'catalog-metrics.json',metrics)
        write_json(stage/'pairs.private.json',{'pairs':pairs})
        counts={r:dict(Counter(correct=sum(p['correct'] for p in pairs if p['role']==r),
                              incorrect=sum(not p['correct'] for p in pairs if p['role']==r),
                              candidates=sum(p['role']==r for p in pairs))) for r in sorted(ROLES)}
        write_json(stage/'support.json',{'cards':len(selected),'roles':counts,'excluded_groups':len(excluded_groups)})
        require(all(digest(p)==manifest['artifacts'][p.name] for p in paths),'Input changed during inference')
        write_json(stage/'manifest.json',{'status':'complete','files_sha256':{p.name:digest(p) for p in stage.iterdir()}})
    return counts


def ranking(pairs, scores, fraction=.1):
    """Expected error capture at a fixed review budget, averaged within score ties."""
    total_errors=sum(not p['correct'] for p in pairs)
    if not pairs or not total_errors:return {'errors':total_errors,'capture':None}
    buckets=defaultdict(list)
    for p,s in zip(pairs,scores):buckets[s].append(p)
    remaining=len(pairs)*fraction; captured=0.
    for score in sorted(buckets):
        ps=buckets[score];taken=min(remaining,len(ps))
        captured+=taken/len(ps)*sum(not p['correct'] for p in ps)
        remaining-=taken
        if remaining<=0:break
    return {'review_fraction':fraction,'errors':total_errors,'expected_captured':captured,'capture':captured/total_errors}


def experiment(pairs):
    parts={r:[p for p in pairs if p['role']==r] for r in ROLES}
    groups={r:{p['group'] for p in ps} for r,ps in parts.items()}
    require(not any(groups[a]&groups[b] for a,b in [('fit','calibration'),('fit','diagnostic'),('calibration','diagnostic')]),'Family leakage')
    require(len(parts['fit'])>=200 and len(groups['fit'])>=20 and min(sum(p['correct'] for p in parts['fit']),sum(not p['correct'] for p in parts['fit']))>=20,'Insufficient fit support')
    require(all(len(groups[r])>=10 and 0<sum(p['correct'] for p in parts[r])<len(parts[r]) for r in ('calibration','diagnostic')),'Insufficient calibration/diagnostic support')
    weights=fit_logistic([p['features'] for p in parts['fit']],[int(p['correct']) for p in parts['fit']])
    platt=fit_logistic([{'intercept':1.,'logit':logit(weights,p['features'])} for p in parts['calibration']],
                     [int(p['correct']) for p in parts['calibration']])
    results={}
    for role in sorted(ROLES):
        ps=parts[role]
        scores={'fixed':[p['fixed'] for p in ps],
                'logistic':[sigmoid(logit(weights,p['features'])) for p in ps],
                'platt':[sigmoid(logit(platt,{'intercept':1.,'logit':logit(weights,p['features'])})) for p in ps]}
        results[role]={v:summary(ps,ss)|{'review_10pct':ranking(ps,ss)} for v,ss in scores.items()}
    return {'results':results,'weights':weights,'platt':platt}


def verified_directory(folder):
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    require(manifest.get('status')=='complete','Incomplete prepared directory')
    for name,sha in manifest['files_sha256'].items():
        require(name not in {'.','..'} and Path(name).name==name and digest(folder/name)==sha,'Prepared artifact hash mismatch')
    return manifest


def finalize(prepared, human, output):
    """Release an advisory artifact only after the frozen acceptance gates pass."""
    from goodsai.learned_confidence import (FORMAT, FEATURE_VERSION, profile_fingerprint,
                                           predict_score, explain, validate_model)
    verified_directory(prepared);verified_directory(human)
    freeze=json.loads((prepared/'freeze.json').read_text(encoding='utf-8'))
    human_freeze=json.loads((human/'freeze.json').read_text(encoding='utf-8'))
    require(freeze['code_sha256']==human_freeze['code_sha256']==code_hash(ROOT),
            'Prepared features must match current runtime source')
    pairs=json.loads((prepared/'pairs.private.json').read_text(encoding='utf-8'))['pairs']
    human_pairs=json.loads((human/'pairs.private.json').read_text(encoding='utf-8'))['pairs']
    config=load_config();fit=experiment(pairs)
    # Scope eligibility uses fit counts only. No diagnostic threshold selection.
    scopes=Counter(p['scope'] for p in pairs if p['role']=='fit')
    output.parent.mkdir(parents=True,exist_ok=True)
    with preparation_directory(output,prepared/'manifest.json',human/'manifest.json') as stage:
        write_json(stage/'fit-report.json',fit)
        model={'format':FORMAT,'feature_version':FEATURE_VERSION,'reference_kind':'catalog_silver',
            'profile_sha256':profile_fingerprint(config),'weights':fit['weights'],'platt':fit['platt'],
            'supported_scopes':sorted(s for s,n in scopes.items() if n>=30),
            'provenance':{'prepared_manifest_sha256':digest(prepared/'manifest.json'),
                          'fit_report_sha256':digest(stage/'fit-report.json'),'independent_reference':False}}
        validate_model(model,config)
        runtime_report={};slices={}
        for role in sorted(ROLES):
            ps=[p for p in pairs if p['role']==role]
            raw=[p['fixed'] for p in ps];scores=[predict_score(p['features'],p['scope'],model) for p in ps]
            runtime_report[role]={v:summary(ps,ss)|{'review_10pct':ranking(ps,ss)} for v,ss in [('fixed',raw),('learned',scores)]}
            for dimension in ('category','attribute'):
                for key in sorted({p[dimension] for p in ps}):
                    sub=[p for p in ps if p[dimension]==key]
                    slices[role+':'+dimension+':'+key]={v:summary(sub,[p['fixed'] if v=='fixed' else predict_score(p['features'],p['scope'],model) for p in sub]) for v in ('fixed','learned')}
        hs=[]
        for p in human_pairs:
            rule=next(k[5:] for k in p['features'] if k.startswith('rule='))
            hs.append(predict_score(p['features'],p['category']+':'+p['attribute']+':'+rule,model))
        human_report={'fixed':summary(human_pairs,[p['fixed'] for p in human_pairs]),'learned':summary(human_pairs,hs)}
        d=runtime_report['diagnostic']
        gates={'diagnostic_brier_10pct_gain':d['learned']['brier']<=.9*d['fixed']['brier'],
            'diagnostic_ece_not_worse':d['learned']['ece']<=d['fixed']['ece'],
            'diagnostic_error_capture_not_worse':d['learned']['review_10pct']['capture']>=d['fixed']['review_10pct']['capture'],
            'reviewed_sanity_brier':human_report['learned']['brier']<=human_report['fixed']['brier']+.005}
        require(all(gates.values()),'Learned advisory acceptance gate failed')
        learned_config=deepcopy(config);learned_config['runtime']['confidence']={'version':'learned-v1','model':model}
        predictor=Extractor(learned_config)
        with (stage/'human-predictions.private.jsonl').open('w',encoding='utf-8') as out:
            old=indexed(read_jsonl(human/'fixed.jsonl'))
            for row in read_jsonl(human/'reference.private.jsonl'):
                p=Product.from_dict({k:row[k] for k in ('schema_version','sku_id','category_id','title','description','seller_attributes','source_flags') if k in row})
                prediction=predictor.predict(p);write_line(out,prediction)
                facts=deepcopy(prediction)
                for a,b in zip(facts['attributes'],old[p.sku_id]['attributes']):a['confidence']=b['confidence']
                require(facts==old[p.sku_id],'Runtime changed extraction facts/evidence/decisions')
        baseline_metrics=evaluate(human/'fixed.jsonl',human/'reference.private.jsonl',config)
        learned_metrics=evaluate(stage/'human-predictions.private.jsonl',human/'reference.private.jsonl',learned_config)
        require(baseline_metrics['metrics']==learned_metrics['metrics'],'Runtime changed P/R/F1')
        with (stage/'explanations.private.jsonl').open('w',encoding='utf-8') as out:
            for p in pairs:
                if p['role']=='diagnostic':write_line(out,{'sku_id':p['sku_id'],'attribute':p['attribute'],
                    'fixed':p['fixed'],'catalog_agreement':p['correct'],**explain(p['features'],p['scope'],model)})
        report={'version':'advisory-confidence-v2','reference_kind':'catalog_silver','independent_reference':False,
            'acceptance':gates,'runtime_ready':'opt_in_advisory_only_not_human_probability','new_auto_accept_thresholds':False,
            'roles':runtime_report,'slices':slices,'reviewed_sanity':human_report,
            'reviewed_extraction_metrics':learned_metrics['metrics'],
            'supported_scopes':model['supported_scopes'],
            'diagnostic_scored':sum(p['scope'] in model['supported_scopes'] for p in pairs if p['role']=='diagnostic'),
            'source_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'profile_sha256':model['profile_sha256'],
            'prepared_manifest_sha256':digest(prepared/'manifest.json'),'human_manifest_sha256':digest(human/'manifest.json')}
        write_json(stage/'model.json',model);write_json(stage/'profile.json',learned_config);write_json(stage/'report.json',report)
        write_json(stage/'manifest.json',{'status':'complete','files_sha256':{p.name:digest(p) for p in stage.iterdir()}})
    return report


def verify_runtime(bundle, prepared, release, output):
    """Replay every selected real development card through the integrated scorer."""
    from goodsai.learned_confidence import predict_score
    verified_directory(prepared);verified_directory(release)
    freeze=json.loads((prepared/'freeze.json').read_text(encoding='utf-8'))
    require(freeze['code_sha256']==code_hash(ROOT),'Runtime source differs from prepared features')
    for name,sha in freeze['inputs_sha256'].items():require(digest(bundle/name)==sha,'Bundle input changed')
    products=indexed(read_jsonl(bundle/'input.jsonl'));refs=indexed(read_jsonl(bundle/'reference.jsonl'));metas=indexed(read_jsonl(bundle/'metadata.jsonl'))
    config=load_config(release/'profile.json');model=config['runtime']['confidence']['model'];predictor=Extractor(config)
    old=indexed(read_jsonl(prepared/'predictions.private.jsonl'))
    vectors={(p['sku_id'],p['attribute']):p for p in json.loads((prepared/'pairs.private.json').read_text(encoding='utf-8'))['pairs']}
    rows=[];latency=[];changed=0;scored=0
    output.parent.mkdir(parents=True,exist_ok=True)
    with preparation_directory(output,prepared/'manifest.json',release/'manifest.json') as stage:
        with (stage/'predictions.private.jsonl').open('w',encoding='utf-8') as stream:
            for sku in freeze['selected_skus']:
                start=time.perf_counter();row=predictor.predict(Product.from_dict(products[sku]));latency.append((time.perf_counter()-start)*1000)
                facts=deepcopy(row)
                for a,b in zip(facts['attributes'],old[sku]['attributes']):
                    if a['confidence']!=b['confidence']:changed+=1
                    p=vectors.get((sku,a['attribute']))
                    if p:
                        require(a['confidence']==predict_score(p['features'],p['scope'],model),'Runtime score differs from offline features')
                        scored+=p['scope'] in model['supported_scopes']
                    a['confidence']=b['confidence']
                require(facts==old[sku],'Runtime altered facts, evidence or decisions')
                write_line(stream,row);rows.append(row)
        metrics,_,_=evaluate_rows([products[s] for s in freeze['selected_skus']], [refs[s] for s in freeze['selected_skus']],
                                  [metas[s] for s in freeze['selected_skus']],rows,config,repeats=100)
        report={'cards':len(rows),'known_candidates_scored':scored,'changed_confidence':changed,'value_evidence_decision_changes':0,
            'model_calls':0,'api_cost':0,'latency_ms':{'mean':sum(latency)/len(latency),'p95':sorted(latency)[int(.95*len(latency))]},
            'catalog_metrics':metrics,'source_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()}
        write_json(stage/'report.json',report)
        write_json(stage/'manifest.json',{'status':'complete','files_sha256':{p.name:digest(p) for p in stage.iterdir()}})
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('--bundle',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    p=sub.add_parser('fit');p.add_argument('--prepared',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p=sub.add_parser('finalize');p.add_argument('--prepared',type=Path,required=True);p.add_argument('--human',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    p=sub.add_parser('verify-runtime');p.add_argument('--bundle',type=Path,required=True);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--release',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='prepare':print(json.dumps(prepare(args.bundle,args.output_dir)))
    elif args.command=='finalize':
        r=finalize(args.prepared,args.human,args.output_dir);print(json.dumps({'acceptance':r['acceptance'],'runtime_ready':r['runtime_ready']}))
    elif args.command=='verify-runtime':
        r=verify_runtime(args.bundle,args.prepared,args.release,args.output_dir);print(json.dumps({k:r[k] for k in ('cards','known_candidates_scored','changed_confidence','value_evidence_decision_changes','latency_ms')}))
    else:
        require(not args.output.exists(),'Output exists')
        m=json.loads((args.prepared/'manifest.json').read_text(encoding='utf-8'))
        for n,sha in m['files_sha256'].items():require(digest(args.prepared/n)==sha,'Prepared hash mismatch')
        pairs=json.loads((args.prepared/'pairs.private.json').read_text(encoding='utf-8'))['pairs']
        result=experiment(pairs);write_json(args.output,result)
        print(json.dumps({r:{v:{'brier':s['brier'],'ece':s['ece'],'capture':s['review_10pct']['capture']} for v,s in vs.items()} for r,vs in result['results'].items()}))


if __name__=='__main__':main()
