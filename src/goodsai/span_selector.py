"""Client-validated span IDs; every value is derived from the selected original span."""
import re

from goodsai.candidate_verifier import CandidateVerifier
from goodsai.normalize import NUMBER, UNITS, model_name, numeric
from goodsai.span_index import SpanConfig, build_span_index, visible_view
from goodsai.stages import Candidate
from goodsai.text import visible_span

VERSION = 'span-selector-1'
SYSTEM = ('Выбери только исходный span_id для каждого requested attribute или null. '
          'Ответ только {"attributes":[{"attribute":"...","span_id":"..."}]}. '
          'Запрещены value, quote, пояснения и другие ключи. Не угадывай: если факт не доказан, span_id=null. '
          'Учитывай отрицания, конфликт и принадлежность значения товару на всём source context.')


class SelectorError(ValueError):
    pass


def selection_error(item):
    if (not isinstance(item, dict) or set(item) != {'attribute','span_id'}
            or not isinstance(item['attribute'],str)
            or (item['span_id'] is not None and not isinstance(item['span_id'],str))):
        return 'llm_selector_bad_shape'
    return None


def selector_index(product, max_spans=512):
    config=SpanConfig(max_spans=max_spans)
    index=build_span_index(product,config)
    if index.status != 'available':
        raise SelectorError('llm_selector_index_incomplete')
    return index, config


def selector_payload(product, attributes, max_spans=512):
    index,_=selector_index(product,max_spans)
    ids=[e.span_id for e in index.entries]
    return {'selector_version':VERSION,'index_version':index.algorithm_version,'index_id':index.index_id,
            'spans':[{'span_id':e.span_id,'field':e.field,'start':e.start,'end':e.end,'text':e.surface}
                     for e in index.entries],
            'response_schema':{'type':'object','additionalProperties':False,'required':['attributes'],
                               'properties':{'attributes':{'type':'array','items':{'type':'object',
                                  'additionalProperties':False,'required':['attribute','span_id'],
                                  'properties':{'attribute':{'enum':list(attributes)},'span_id':{'enum':[None,*ids]}}}}}},
            'server_constrained_decoding':False}


def candidate_from_id(product, item, config, *, max_spans=512, gate=None):
    if reason:=selection_error(item):return None,reason
    if item['span_id'] is None:return None,None
    attr=item['attribute']
    if attr not in config['categories'].get(product.category_id,[]):return None,'llm_unknown_attribute'
    try:
        index,span_config=selector_index(product,max_spans)
        span=index.resolve(item['span_id'],product,span_config)
    except (ValueError,SelectorError):return None,'llm_selector_unknown_or_stale_id'
    source=getattr(product,span.field)
    text=visible_span(source,span.start,span.end).strip()
    value=None
    if attr in UNITS:
        from goodsai.llm import PAIR,UNIT_PATTERNS
        pair=PAIR.fullmatch(text) if attr in {'ram_gb','storage_gb'} else None
        try:
            if pair:
                value=numeric(attr,pair['ram' if attr=='ram_gb' else 'rom'],'GB',config['numeric_bounds'])
            else:
                match=re.fullmatch(rf'(?P<n>{NUMBER})\s*(?P<u>{UNIT_PATTERNS[attr]})',text,re.I)
                if match:value=numeric(attr,match['n'],match['u'],config['numeric_bounds'])
        except ValueError:pass
    elif attr in {'brand','color'}:
        table=config['brands' if attr=='brand' else 'colors']
        matches=[canonical for canonical,aliases in table.items()
                 if text.casefold() in {a.casefold() for a in [canonical,*aliases]}]
        if len(matches)==1:value=matches[0]
        elif attr=='brand' and not matches and re.fullmatch(r'[^\W\d_][\w-]{1,59}',text):value=text
    elif attr=='model':value=model_name(text)
    if value is None:return None,'llm_selector_span_not_normalizable'
    candidate=Candidate(attr,value,UNITS.get(attr),span.field,span.start,span.end,span.surface,.6,'llm.'+VERSION)
    gate=gate if gate is not None else CandidateVerifier(product,config)
    reason=gate.reason(candidate)
    return (None,reason) if reason else (candidate,None)
