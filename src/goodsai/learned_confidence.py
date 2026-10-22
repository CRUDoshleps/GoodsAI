"""Portable JSON advisory scoring. Catalog-proxy calibration is not human probability."""
import hashlib
import json
import math
from pathlib import Path

from goodsai.silver_calibration import logit, sigmoid

FORMAT = 'goodsai-advisory-confidence-1'
FEATURE_VERSION = 'text-candidate-1'
GRAMMAR_FILES = ('rules.py','model_rules.py','normalize.py','text.py','candidate_verifier.py',
                 'relation.py','contracts.py','category_registry.py','config.py','verify.py',
                 'confidence.py','learned_confidence.py','silver_calibration.py')


def profile_fingerprint(config):
    root=Path(__file__).parent
    value={'profile':{k:v for k,v in config.items() if k!='runtime'},
           'sources':{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in GRAMMAR_FILES}}
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def validate_model(model, config):
    expected={'format','feature_version','reference_kind','profile_sha256','weights','platt','supported_scopes','provenance'}
    if not isinstance(model,dict) or set(model)!=expected:
        raise ValueError('Invalid advisory confidence artifact fields')
    if (model['format']!=FORMAT or model['feature_version']!=FEATURE_VERSION
            or model['reference_kind']!='catalog_silver'):
        raise ValueError('Unknown advisory model/feature/reference version')
    if model['profile_sha256']!=profile_fingerprint(config):
        raise ValueError('Advisory model does not match extraction/feature profile')
    numeric={'intercept','score','span_length','explicit_role','explicit_unit','cross_field_agreement'}
    for field in ('weights','platt'):
        weights=model[field]
        if not isinstance(weights,dict) or not 1<=len(weights)<=4096:
            raise ValueError('Invalid advisory weights')
        for key,value in weights.items():
            if (not isinstance(key,str) or len(key)>160
                    or (field=='platt' and key not in {'intercept','logit'})
                    or (field=='weights' and key not in numeric and not key.startswith(('attribute=','category=','rule=','field=')))
                    or type(value) not in (int,float) or not math.isfinite(value) or abs(value)>100):
                raise ValueError('Invalid advisory feature or non-finite weight')
    if set(model['platt'])!={'intercept','logit'} or model['platt']['logit']<=0:
        raise ValueError('Advisory calibration must be monotonic')
    scopes=model['supported_scopes']
    if (not isinstance(scopes,list) or not scopes or len(scopes)>4096
            or any(not isinstance(s,str) or not 1<=len(s)<=200 for s in scopes)
            or len(set(scopes))!=len(scopes)):
        raise ValueError('Invalid supported scopes')
    for scope in scopes:
        parts=scope.split(':')
        if len(parts)!=3 or parts[1] not in config['categories'].get(parts[0],[]):
            raise ValueError('Advisory scope outside configured attributes')
    provenance=model['provenance']
    if (not isinstance(provenance,dict) or set(provenance)!={'prepared_manifest_sha256','fit_report_sha256','independent_reference'}
            or provenance['independent_reference'] is not False):
        raise ValueError('Catalog proxy provenance must remain non-independent')
    for key in ('prepared_manifest_sha256','fit_report_sha256'):
        v=provenance[key]
        if not isinstance(v,str) or len(v)!=64 or any(c not in '0123456789abcdef' for c in v):
            raise ValueError('Invalid advisory provenance hash')
    return model


def scope_key(category, attribute, rule_id):
    return category+':'+attribute+':'+rule_id


def predict_score(vector, scope, model):
    if scope not in model['supported_scopes']:
        return vector['score']
    raw=logit(model['weights'],vector)
    return round(sigmoid(logit(model['platt'],{'intercept':1.,'logit':raw})),6)


def explain(vector, scope, model):
    if scope not in model['supported_scopes']:
        return {'status':'fallback_unsupported_scope','score':vector['score']}
    contributions={k:model['weights'].get(k,0.)*v for k,v in vector.items()}
    return {'status':'catalog_proxy_advisory','score':predict_score(vector,scope,model),
            'logit_contributions':contributions,'pre_calibration_logit':sum(contributions.values()),
            'calibration_kind':'catalog_proxy_platt_not_human_probability'}


def metadata(config):
    policy=config['runtime'].get('confidence')
    if policy is None:
        return None
    result={'version':policy['version'],'confidence_kind':'heuristic','human_probability_calibrated':False,
            'new_auto_accept_thresholds':False}
    if policy['version']=='learned-v1':
        model=policy['model']
        result.update(reference_kind='catalog_silver',supported_scopes=len(model['supported_scopes']),
                      unsupported_scope='fixed_score_fallback',
                      model_sha256=hashlib.sha256(json.dumps(model,sort_keys=True,separators=(',',':')).encode()).hexdigest())
    return result
