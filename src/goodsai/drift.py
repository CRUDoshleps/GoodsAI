"""Local aggregate drift versus a frozen compatible baseline; never a quality estimate."""
from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import re

VERSION='drift-1'
METRICS=('unsupported','abstain','review','conflict','evidence_reject','llm_result','llm_routed','provider_reject')


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def snapshot(products, predictions, config, identity, batch_sha256, routing_counts=None):
    """Only allowlisted numeric aggregates leave this boundary; IDs/text/reasons never do."""
    if set(identity)!={'schema','config_sha256','policy_sha256','producer_sha256'} or identity['schema']!='0.1':
        raise ValueError('Invalid aggregate identity')
    if any(not re.fullmatch('[0-9a-f]{64}',v) for k,v in identity.items() if k!='schema'):
        raise ValueError('Aggregate identities must be hashes')
    if not re.fullmatch('[0-9a-f]{64}',batch_sha256):raise ValueError('Invalid batch hash')
    from goodsai.contracts import validate_prediction
    categories=Counter();lengths=Counter();cohorts={};n=0
    def count(key, flags):
        c=cohorts.setdefault(key,dict(count=0,**{m:0 for m in METRICS}))
        c['count']+=1
        for metric in METRICS:c[metric]+=int(flags.get(metric,False))
    products=list(products);predictions=list(predictions)
    if len(products)!=len(predictions):raise ValueError('Prediction/input count mismatch')
    seen=set()
    for product,row in zip(products,predictions):
        if row.get('sku_id')!=product.sku_id or product.sku_id in seen:raise ValueError('Prediction/input identity mismatch')
        seen.add(product.sku_id)
        validate_prediction(row,config,product)
        cat=product.category_id if product.category_id in config['categories'] and re.fullmatch(r'\d{1,10}',product.category_id) else '__other__'
        categories[cat]+=1;n+=1
        size=len(product.title)+len(product.description or '')
        lengths[next((str(bound) for bound in (128,512,2048,8192) if size<=bound),'over_8192')]+=1
        unsupported=row['status']=='unsupported_category'
        count('__all__',{'unsupported':unsupported})
        for a in row['attributes']:
            reasons=a['reason_codes']
            from goodsai.config import ATTRIBUTES
            attribute=a['attribute'] if a['attribute'] in ATTRIBUTES else '__other_attribute__'
            count(cat+':'+attribute,{
                'abstain':a['decision']=='abstain','review':a['decision']=='review',
                'conflict':any('conflict' in r for r in reasons),
                'evidence_reject':any(r in {'verifier_bad_evidence','llm_quote_not_found','llm_span_not_visible',
                                           'verifier_foreign_entity','llm_foreign_entity'} for r in reasons),
                'llm_result':a['method']=='llm',
                'provider_reject':any(r in {'llm_auth_failed','llm_rate_limited','llm_server_error','llm_timeout',
                    'llm_network_error','llm_malformed_response','llm_malformed_json','llm_response_too_large'} for r in reasons)})
    if routing_counts is not None:
        routed,seen=routing_counts
        if type(routed) is not int or type(seen) is not int or seen!=n or not 0<=routed<=n:
            raise ValueError('Routing counters do not match the stream')
        cohorts['__routing__']=dict(count=n,**{m:0 for m in METRICS})
        cohorts['__routing__']['llm_routed']=routed
    return {'version':VERSION,'identity':dict(identity),'batch_sha256':batch_sha256,'count':n,
            'categories':dict(categories),'lengths':dict(lengths),'cohorts':cohorts,
            'quality':{'precision':None,'recall':None,'f1':None,'reason':'reviewed_labels_required'}}


@dataclass(frozen=True)
class DriftPolicy:
    min_support:int
    rate_delta:float
    js_threshold:float
    persistence:int
    clear_ratio:float=.5

    def __post_init__(self):
        if type(self.min_support) is not int or self.min_support<20:raise ValueError('Minimum support must be >=20')
        if type(self.persistence) is not int or not 1<=self.persistence<=100:raise ValueError('Invalid persistence')
        for name in ('rate_delta','js_threshold','clear_ratio'):
            v=getattr(self,name)
            if type(v) not in (int,float) or not math.isfinite(v) or not 0<v<1:raise ValueError('Invalid drift policy')


def interval(k,n):
    # Wilson 95% interval: uncertainty gate, not a probability of drift.
    if not n:return (0,1)
    z=1.959963984540054;p=k/n;den=1+z*z/n
    center=(p+z*z/(2*n))/den
    width=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return max(0,center-width),min(1,center+width)


def js_divergence(left,right):
    a,b=sum(left.values()),sum(right.values())
    if not a or not b:return None
    result=0
    for key in left.keys()|right.keys():
        p,q=left.get(key,0)/a,right.get(key,0)/b;m=(p+q)/2
        if p:result+=.5*p*math.log2(p/m)
        if q:result+=.5*q*math.log2(q/m)
    return result


def validate_snapshot(value):
    if not isinstance(value,dict) or value.get('version')!=VERSION:raise ValueError('Invalid aggregate snapshot')
    if set(value)!={'version','identity','batch_sha256','count','categories','lengths','cohorts','quality'}:
        raise ValueError('Unknown aggregate fields')
    if type(value['count']) is not int or value['count']<0:raise ValueError('Invalid aggregate count')
    for distribution in ('categories','lengths'):
        if (not isinstance(value[distribution],dict) or any(type(n) is not int or n<0 for n in value[distribution].values())
                or sum(value[distribution].values())!=value['count']):raise ValueError('Invalid histogram')
    from goodsai.config import ATTRIBUTES
    for name in value['categories']:
        if name!='__other__' and not re.fullmatch(r'\d{1,10}',name):raise ValueError('Unsafe category label')
    if set(value['lengths'])-{'128','512','2048','8192','over_8192'}:raise ValueError('Unsafe length histogram')
    for name,c in value['cohorts'].items():
        if name not in {'__all__','__routing__'}:
            parts=name.split(':')
            if (len(parts)!=2 or (parts[0]!='__other__' and not re.fullmatch(r'\d{1,10}',parts[0]))
                    or parts[1] not in ATTRIBUTES|{'__other_attribute__'}):raise ValueError('Unsafe cohort label')
        if set(c)!={'count',*METRICS} or type(c['count']) is not int or c['count']<0:raise ValueError('Invalid cohort')
        if any(type(c[m]) is not int or not 0<=c[m]<=c['count'] for m in METRICS):raise ValueError('Invalid cohort metric')


def compare(baseline,current,policy,state=None):
    validate_snapshot(baseline);validate_snapshot(current)
    if baseline['identity']!=current['identity']:raise ValueError('Incompatible baseline: schema/config/policy/producer changed')
    baseline_hash=fingerprint(baseline);policy_hash=fingerprint(asdict(policy))
    state=state or {'baseline_sha256':baseline_hash,'policy_sha256':policy_hash,'seen':[],'signals':{}}
    if state.get('baseline_sha256')!=baseline_hash or state.get('policy_sha256')!=policy_hash:
        raise ValueError('Drift state belongs to another baseline/policy')
    state=json.loads(json.dumps(state))
    window=fingerprint(current)
    report={'version':VERSION,'baseline_sha256':baseline_hash,'window_sha256':window,'policy_sha256':policy_hash,
            'alerts':[],'resolved':[],'suppressed':[],'measurements':[],
            'quality':{'precision':None,'recall':None,'f1':None},'duplicate_window':window in state['seen']}
    if report['duplicate_window']:return report,state
    state['seen']=(state['seen']+[window])[-1024:]
    def signal(key,value,trigger,clear,details):
        item=state['signals'].setdefault(key,{'streak':0,'active':False})
        item['streak']=item['streak']+1 if trigger else 0
        if item['active'] and clear:
            item['active']=False;report['resolved'].append(key)
        if not item['active'] and item['streak']>=policy.persistence:
            item['active']=True
            report['alerts'].append(dict(signal=key,value=value,reason='persistent_proxy_shift',
                action='Collect a local audit sample; verify configuration/provider before any manual route change.',
                aggregate_source=report['window_sha256'],baseline_sha256=baseline_hash,**details))
    for key in baseline['cohorts'].keys()|current['cohorts'].keys():
        base=baseline['cohorts'].get(key);cur=current['cohorts'].get(key)
        if not base or not cur or min(base['count'],cur['count'])<policy.min_support:
            report['suppressed'].append({'slice':key,'reason':'insufficient_support'})
            for name in METRICS:
                if key+':'+name in state['signals']:state['signals'][key+':'+name]['streak']=0
            continue
        for name in METRICS:
            b,c=base[name]/base['count'],cur[name]/cur['count']
            blo,bhi=interval(base[name],base['count']);clo,chi=interval(cur[name],cur['count'])
            delta=c-b;bounds=[clo-bhi,chi-blo]
            report['measurements'].append({'slice':key,'metric':name,'baseline':[base[name],base['count']],
                'current':[cur[name],cur['count']],'delta':delta,'delta_interval':bounds})
            # Review increases are not automatically degradation; all alerts are proxy diagnostics.
            signal(key+':'+name,delta,bounds[0]>policy.rate_delta,
                   delta<policy.rate_delta*policy.clear_ratio,
                   {'slice':key,'metric':name,'delta_interval':bounds,'baseline_rate':b,'current_rate':c})
    for name in ('categories','lengths'):
        if min(baseline['count'],current['count'])<policy.min_support:
            report['suppressed'].append({'slice':name,'reason':'insufficient_support'});continue
        js=js_divergence(baseline[name],current[name])
        report['measurements'].append({'distribution':name,'js_divergence':js})
        signal('distribution:'+name,js,js is not None and js>policy.js_threshold,
               js is not None and js<policy.js_threshold*policy.clear_ratio,
               {'slice':name,'metric':'js_divergence'})
    return report,state


def main():
    import argparse
    from goodsai.contracts import Product,load_config
    from goodsai.data import read_jsonl,digest
    from goodsai.storage import atomic_text,output_lock
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    s=sub.add_parser('snapshot')
    for key in ('input','predictions','manifest','output'):s.add_argument('--'+key,type=Path,required=True)
    s.add_argument('--config')
    c=sub.add_parser('compare')
    for key in ('baseline','current','policy','state'):c.add_argument('--'+key,type=Path,required=True)
    args=p.parse_args()
    if args.command=='snapshot':
        m=json.loads(args.manifest.read_text(encoding='utf-8'));config=load_config(args.config)
        if m.get('input_sha256')!=digest(args.input) or m.get('output_sha256')!=digest(args.predictions):
            raise ValueError('Prediction pair hash mismatch')
        identity={'schema':'0.1','config_sha256':m['config_sha256'],
                  'policy_sha256':m.get('runtime_policy_sha256',fingerprint(config['runtime'])),
                  'producer_sha256':fingerprint({'code':m['code_sha256'],'model':m.get('llm',{}).get('model'),
                                                'revision':m.get('llm',{}).get('model_revision')})}
        result=snapshot([Product.from_dict(r) for r in read_jsonl(args.input)],list(read_jsonl(args.predictions)),
                        config,identity,digest(args.input),
                        (m['llm']['cards_routed'],m['llm']['cards_seen']) if m.get('llm',{}).get('enabled') else None)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=True,allow_nan=False,indent=2)
    else:
        def read(path):return json.loads(path.read_text(encoding='utf-8'))
        # One lock covers read/compare/write so concurrent batches cannot lose hysteresis state.
        from goodsai.storage import _atomic_text
        with output_lock(args.state):
            report,state=compare(read(args.baseline),read(args.current),DriftPolicy(**read(args.policy)),
                                 read(args.state) if args.state.exists() else None)
            with _atomic_text(args.state) as f:json.dump(state,f,allow_nan=False)
        print(json.dumps(report,ensure_ascii=True,allow_nan=False))


if __name__=='__main__':main()
