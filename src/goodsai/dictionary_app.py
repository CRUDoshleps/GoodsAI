"""Separate local dictionary console; publication needs an authenticated schema owner."""
import argparse
import base64
import hashlib
import re
import hmac
import json
import os
from pathlib import Path

from fastapi import FastAPI,Request
from starlette.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse,JSONResponse

from goodsai.contracts import load_config,Product
from goodsai.dictionary import DictionaryStore,VersionConflict

HTML='''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>GoodsAI · Словари</title><style>
body{font:16px system-ui;background:#f5f6f8;color:#17212d;max-width:1080px;margin:40px auto;padding:0 20px}
section,article{background:white;border:1px solid #dbe1e7;border-radius:12px;padding:20px;margin:16px 0}
h1{font-size:30px}label{display:block;margin:12px 0}input,select,button{font:inherit;padding:9px;border:1px solid #bbc6d0;border-radius:6px}
button{background:#155de9;color:white;cursor:pointer;margin:4px}input{max-width:100%;box-sizing:border-box}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:8px;border-bottom:1px solid #eee}
small{color:#526170}#message{white-space:pre-wrap;color:#a21b27}code{overflow-wrap:anywhere}details{margin:12px 0}
</style><h1>Словари GoodsAI</h1><p>Предложите написание → проверьте влияние → передайте на review → опубликуйте версию.</p>
<section><label>Ключ доступа <input id="token" type="password" autocomplete="off"></label><button id="connect">Подключиться</button>
<small>Ключ хранится только в памяти страницы. Публикует владелец схемы; автор не утверждает свою правку.</small><p id="identity"></p><p id="message" role="status"></p></section>
<section><h2>Действующая версия</h2><code id="version">Подключитесь для просмотра</code><p id="dictversion"></p><button id="download">Скачать опубликованный профиль</button>
<label>Поиск <input id="search"></label><div id="values"></div>
<details><summary>Откат к проверенной версии</summary><label>Version ID <input id="target"></label><button id="rollback">Создать версию отката</button></details></section>
<section><h2>Новое предложение</h2><form id="proposal"><label>Поле <select id="attribute"><option value="brand">Бренд</option><option value="color">Цвет</option></select></label>
<label>Каноническое значение <input id="canonical" list="canonicals" required maxlength="128"><datalist id="canonicals"></datalist></label>
<label>Новое написание <input id="alias" required maxlength="128"></label>
<label>Источник <select id="kind"><option value="manual">Ручное предложение</option><option value="confirmed_feedback">Подтверждённое исправление</option></select></label>
<label>Ссылка на подтверждение / заметка <input id="reference" required maxlength="256"></label>
<label><input type="checkbox" id="scope" required> Учитываю влияние на все категории с этим полем</label>
<button>Сохранить draft</button><small>Неизвестное значение останется предложением. Новые факты и единицы через alias не добавляются.</small></form></section>
<section><h2>Предложения и проверка влияния</h2><div id="proposals"></div></section>
<script>
let state=null;let token='';
const $=id=>document.getElementById(id);
function el(tag,text){let n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;}
function message(text){$('message').textContent=text;}
async function api(path,method='GET',body){const r=await fetch('/dictionary'+path,{method,headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});const data=await r.json();if(!r.ok)throw Error(data.error||'Не удалось выполнить действие');return data;}
function button(label,action){let n=el('button',label);n.type='button';n.onclick=()=>action().catch(e=>message(e.message));return n;}
function values(){if(!state)return;let fragment=document.createDocumentFragment();const filter=$('search').value.toLowerCase();
 for(const [field,table] of Object.entries({brand:state.current.config.brands,color:state.current.config.colors})){
  let rows=el('table');rows.append(el('caption',field==='brand'?'Бренды':'Цвета'));
  for(const [canonical,aliases] of Object.entries(table)){if(!(canonical+' '+aliases.join(' ')).toLowerCase().includes(filter))continue;let tr=el('tr');tr.append(el('th',canonical),el('td',aliases.join(', ')));rows.append(tr);}fragment.append(rows);}
 $('values').replaceChildren(fragment);
 let options=Object.keys(state.current.config[$('attribute').value==='brand'?'brands':'colors']).map(v=>{let o=el('option');o.value=v;return o;});$('canonicals').replaceChildren(...options);}
async function refresh(){state=await api('/state');$('version').textContent=state.current.id;$('dictversion').textContent=state.current.config.dictionary_version;$('identity').textContent=state.account.name+' · '+state.account.role;values();let cards=[];
 for(const p of state.proposals){let card=el('article');card.append(el('h3',p.payload.alias+' → '+p.payload.canonical),el('p',p.status+' · автор '+p.author+' · review '+(p.reviewer||'ожидается')));
  if(p.validation_error)card.append(el('p',p.validation_error));
  if(p.impact){card.append(el('p','Проверено карточек: '+p.impact.cards+' · изменений: '+p.impact.changes.length));card.append(el('small','Raw source не изменён; без reviewed labels TP/FP/FN недоступны.'));
   let table=el('table');for(const change of p.impact.changes){let tr=el('tr');tr.append(el('td',change.sku_id+' / '+change.attribute),el('td',String(change.before.value)+' → '+String(change.after.value)),el('td',change.after.decision));table.append(tr);}card.append(table);
   let details=el('details');details.append(el('summary','Метрики и fingerprints'),el('pre',JSON.stringify(p.impact.metrics,null,2)+'\\nsource SHA: '+p.impact.source_sha256));card.append(details);}
  if(p.status==='draft'){card.append(button('Рассчитать impact',async()=>{await api('/proposals/'+p.id+'/impact','POST',{revision:p.revision});await refresh();}));card.append(button('Подтвердить review',async()=>{await api('/proposals/'+p.id+'/review','POST',{revision:p.revision});await refresh();}));}
  if(p.status==='review')card.append(button('Опубликовать',async()=>{await api('/proposals/'+p.id+'/publish','POST',{revision:p.revision,expected_version:state.current.id});await refresh();message('Новая версия опубликована. Новый run использует её только с явно выбранным профилем.');}));cards.push(card);}
 $('proposals').replaceChildren(...cards);}
$('connect').onclick=async()=>{try{token=$('token').value;$('token').value='';await refresh();message('Подключено');}catch(e){message(e.message);}};
$('search').oninput=values;$('attribute').onchange=values;
$('proposal').onsubmit=async e=>{e.preventDefault();try{let attribute=$('attribute').value;await api('/proposals','POST',{base:state.current.id,attribute,canonical:$('canonical').value,alias:$('alias').value,categories:Object.keys(state.current.config.categories).filter(c=>state.current.config.categories[c].includes(attribute)),provenance:{kind:$('kind').value,reference:$('reference').value}});await refresh();message('Draft сохранён; действующая версия не изменилась.');}catch(e){message(e.message);}};
$('download').onclick=()=>{if(!state)return;const blob=new Blob([JSON.stringify(state.current.config,null,2)],{type:'application/json'});let a=el('a');a.href=URL.createObjectURL(blob);a.download='goodsai-'+state.current.id.slice(0,12)+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);};
$('rollback').onclick=async()=>{try{await api('/rollback','POST',{target:$('target').value,expected_version:state.current.id});await refresh();message('Создана новая версия отката.');}catch(e){message(e.message);}};
</script></html>'''


def create_app(store,accounts,products=(),*,reference=None):
    """Accounts are trusted server configuration: token -> {name, role}; never request roles."""
    for token,account in accounts.items():
        if (not isinstance(token,str) or len(token)<16 or set(account)!={'name','role'}
                or not isinstance(account['name'],str) or not account['name']
                or account['role'] not in {'reader','proposer','reviewer','owner'}):raise ValueError('Invalid dictionary accounts')
    products=tuple(products)
    app=FastAPI(title='GoodsAI Dictionary Console',docs_url=None,redoc_url=None,openapi_url=None)
    @app.middleware('http')
    async def response_headers(request,call_next):
        response=await call_next(request)
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='DENY'
        script=base64.b64encode(hashlib.sha256(re.search(r'<script>(.*?)</script>',HTML,re.S)[1].encode()).digest()).decode()
        style=base64.b64encode(hashlib.sha256(re.search(r'<style>(.*?)</style>',HTML,re.S)[1].encode()).digest()).decode()
        response.headers['Content-Security-Policy']=f"default-src 'self'; script-src 'sha256-{script}'; style-src 'sha256-{style}'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response
    @app.get('/',response_class=HTMLResponse)
    def page():return HTML
    @app.api_route('/dictionary/{operation:path}',methods=['GET','POST'])
    async def dispatch(operation,request:Request):
        authorization=request.headers.get('authorization','')
        supplied=authorization[7:] if authorization.startswith('Bearer ') else ''
        account=next((a for token,a in accounts.items() if hmac.compare_digest(token.encode('utf-8'),supplied.encode('utf-8'))),None)
        if account is None:return JSONResponse({'error':'Требуется ключ доступа'},status_code=401)
        allowed={'reader':set(),'proposer':{'draft','impact'},'reviewer':{'impact','review'},'owner':{'draft','impact','review','publish','rollback'}}
        try:
            if request.method=='GET' and operation=='state':
                proposals=store.proposals()
                for p in proposals:
                    try:store.candidate(p);p['validation_error']=None
                    except ValueError as e:p['validation_error']=str(e)
                return {'account':account,'current':store.current(),'proposals':proposals}
            if request.method!='POST':return JSONResponse({'error':'Неизвестная операция'},status_code=404)
            # Bounded before decoding; no arbitrary server-side file paths or input text in requests.
            body=bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body)>16384:return JSONResponse({'error':'Слишком большой запрос'},status_code=413)
            data=json.loads(body.decode('utf-8'))
            if not isinstance(data,dict):raise ValueError('Expected an object')
            parts=operation.split('/')
            action='draft' if operation=='proposals' else 'rollback' if operation=='rollback' else parts[-1]
            if action not in allowed[account['role']]:return JSONResponse({'error':'Недостаточно прав'},status_code=403)
            if action=='draft':
                expected={'base','attribute','canonical','alias','categories','provenance'}
                if set(data)!=expected:raise ValueError('Invalid proposal fields')
                return store.draft(author=account['name'],**data)
            if action=='rollback':
                if set(data)!={'target','expected_version'}:raise ValueError('Invalid rollback fields')
                return store.rollback(owner=account['name'],**data)
            if len(parts)!=3 or parts[0]!='proposals':raise ValueError('Invalid proposal operation')
            if set(data)!=({'revision','expected_version'} if action=='publish' else {'revision'}):raise ValueError('Invalid operation fields')
            if type(data['revision']) is not int or data['revision']<0:raise ValueError('Invalid proposal revision')
            if action=='impact':return await run_in_threadpool(store.impact,parts[1],data['revision'],products,reference=reference)
            if action=='review':return store.review(parts[1],data['revision'],account['name'])
            if action=='publish':return store.publish(parts[1],data['revision'],data['expected_version'],account['name'])
            return JSONResponse({'error':'Неизвестная операция'},status_code=404)
        except VersionConflict as exc:return JSONResponse({'error':str(exc)},status_code=409)
        except (ValueError,KeyError,TypeError,RecursionError):
            # Store diagnostics are rendered safely in GET state; malformed POST details are not echoed.
            return JSONResponse({'error':'Предложение или переход недопустимы; проверьте scope, impact, автора и версию'},status_code=422)
    return app


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',type=Path,default=Path('outputs/dictionary.sqlite'))
    p.add_argument('--config');p.add_argument('--development',type=Path);p.add_argument('--reference',type=Path)
    p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=8001)
    args=p.parse_args()
    try:accounts=json.loads(os.environ.get('GOODSAI_DICTIONARY_ACCOUNTS','{}'))
    except (ValueError,TypeError):raise ValueError('Invalid dictionary accounts configuration') from None
    from goodsai.data import read_jsonl
    products=tuple(Product.from_dict(r) for r in read_jsonl(args.development)) if args.development else ()
    store=DictionaryStore(args.db,load_config(args.config))
    app=create_app(store,accounts,products,reference=args.reference)
    import uvicorn
    uvicorn.run(app,host=args.host,port=args.port,access_log=False)


if __name__=='__main__':main()
