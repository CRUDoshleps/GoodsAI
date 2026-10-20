"""Explainable human-work ordering, isolated from extraction and training selection."""
from collections import Counter
from dataclasses import asdict,dataclass
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import time

VERSION='review-priority-1'


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def finite(value):return type(value) in (float,int) and math.isfinite(value)


@dataclass(frozen=True)
class ReviewTask:
    task_id:str
    category_id:str
    attribute:str
    created_at:float
    reason_codes:tuple[str,...]
    required:bool=False
    decision:str='review'

    def __post_init__(self):
        if any(not isinstance(v,str) or not v.strip() or len(v)>128 for v in (self.task_id,self.category_id,self.attribute)):
            raise ValueError('Invalid review identifiers')
        if not finite(self.created_at) or self.created_at<0 or type(self.required) is not bool:raise ValueError('Invalid review task')
        if (self.decision not in {'review','abstain'} or not isinstance(self.reason_codes,(tuple,list))
                or any(not isinstance(v,str) or len(v)>128 for v in self.reason_codes)):raise ValueError('Invalid review reasons')


@dataclass(frozen=True)
class RankPolicy:
    version:str=VERSION
    cycle:int=10
    rare_max_count:int=5
    max_demand_weight:float=2
    demand_approval:str|None=None
    audit_seed:str='review-audit-v1'

    def __post_init__(self):
        if self.version!=VERSION:raise ValueError('Unknown rank policy')
        if type(self.cycle) is not int or not 4<=self.cycle<=100:raise ValueError('Invalid quota cycle')
        if type(self.rare_max_count) is not int or self.rare_max_count<1:raise ValueError('Invalid rare support')
        if not finite(self.max_demand_weight) or not 1<=self.max_demand_weight<=3:raise ValueError('Invalid demand cap')
        if not isinstance(self.audit_seed,str) or not self.audit_seed:raise ValueError('Invalid audit seed')
        if self.demand_approval is not None and (not isinstance(self.demand_approval,str) or not self.demand_approval.strip()):
            raise ValueError('Invalid demand approval')


def rank(tasks,policy,*,now,demand=None,cursor=0,limit=None):
    if not finite(now) or now<0 or type(cursor) is not int or cursor<0:raise ValueError('Invalid ranking clock/cursor')
    tasks=list(tasks)
    if len({t.task_id for t in tasks})!=len(tasks):raise ValueError('Duplicate review task')
    if limit is None:limit=len(tasks)
    if type(limit) is not int or limit<0:raise ValueError('Invalid rank limit')
    weights={}
    if demand is not None:
        if (not policy.demand_approval or set(demand)!={'approval','weights'}
                or demand['approval']!=policy.demand_approval or not isinstance(demand['weights'],dict)):
            raise ValueError('Demand requires an explicitly approved aggregate profile')
        if any(not isinstance(k,str) or not finite(v) or not 1<=v<=policy.max_demand_weight for k,v in demand['weights'].items()):
            raise ValueError('Invalid aggregate demand weights')
        weights=demand['weights']
    counts=Counter(t.category_id for t in tasks)
    rows={}
    for t in tasks:
        if t.created_at>now:raise ValueError('Review task lies in the future')
        critical=any('conflict' in r or r.startswith(('verifier_','llm_quote_','llm_span_')) for r in t.reason_codes)
        band=0 if critical else 1 if t.required and t.decision=='abstain' else 2
        age=now-t.created_at;weight=weights.get(t.category_id+':'+t.attribute,1)
        rows[t.task_id]={'task':t,'band':band,'age_seconds':age,'demand_weight':weight,
                         'rare':counts[t.category_id]<=policy.rare_max_count,
                         'audit_key':digest([policy.audit_seed,t.task_id])}
    selected=[]
    for position in range(min(limit,len(rows))):
        slot=(cursor+position)%policy.cycle
        reason='severity_age'
        pool=list(rows.values())
        if slot==policy.cycle-3:
            reason='oldest_quota';key=lambda r:(-r['age_seconds'],r['task'].task_id)
        elif slot==policy.cycle-2 and any(r['rare'] for r in pool):
            reason='rare_quota';pool=[r for r in pool if r['rare']]
            key=lambda r:(r['band'],-r['age_seconds'],r['task'].task_id)
        elif slot==policy.cycle-1:
            reason='audit_quota';key=lambda r:(r['audit_key'],r['task'].task_id)
        else:
            # Demand is bounded and stays inside severity bands. Aging and quotas
            # are independent of popularity; confidence is never read as P(error).
            key=lambda r:(r['band'],-(r['age_seconds']//3600),-r['demand_weight'],r['task'].task_id)
        chosen=min(pool,key=key);t=chosen['task'];del rows[t.task_id]
        selected.append({'rank':position+1,'task_id':t.task_id,'category_id':t.category_id,'attribute':t.attribute,
                         'decision':t.decision,'required':t.required,'policy_version':policy.version,
                         'policy_sha256':digest(asdict(policy)),
                         'priority':{k:chosen[k] for k in ('band','age_seconds','demand_weight','rare')}|{'selected_by':reason,'quota_slot':slot}})
    return {'policy_version':policy.version,'policy_sha256':digest(asdict(policy)),'cursor':cursor,
            'next_cursor':cursor+len(selected),'demand':'approved_aggregates' if demand is not None else 'equal_weights',
            'rows':selected}


class QueueAudit:
    """Append-only local operator sessions. Outcomes are declared development feedback."""
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS actions (id INTEGER PRIMARY KEY, task_id TEXT, category TEXT, '
                       'policy_hash TEXT, actor TEXT, started REAL, finished REAL, wait_seconds REAL, '
                       'mandatory INTEGER, critical INTEGER, rare INTEGER, correct INTEGER)')
            db.execute('CREATE UNIQUE INDEX IF NOT EXISTS action_identity ON actions(task_id,policy_hash)')
    def connect(self):return sqlite3.connect(self.path,timeout=10)
    def begin(self,row,actor,*,now=None):
        now=time.time() if now is None else now
        if not finite(now) or now<0 or not isinstance(actor,str) or not actor.strip():raise ValueError('Invalid audit actor/time')
        with self.connect() as db:
            cursor=db.execute('INSERT INTO actions(task_id,category,policy_hash,actor,started,wait_seconds,mandatory,critical,rare) '
                              'VALUES(?,?,?,?,?,?,?,?,?)',(row['task_id'],row['category_id'],row['policy_sha256'],actor,now,
                              row['priority']['age_seconds'],int(row['required']),int(row['priority']['band']==0),int(row['priority']['rare'])))
            return cursor.lastrowid
    def finish(self,action_id,*,correct,now=None):
        now=time.time() if now is None else now
        if type(correct) is not bool or not finite(now):raise ValueError('Invalid feedback')
        with self.connect() as db:
            row=db.execute('SELECT started,finished FROM actions WHERE id=?',(action_id,)).fetchone()
            if not row or row[1] is not None or now<=row[0]:raise ValueError('Invalid or already completed session')
            db.execute('UPDATE actions SET finished=?,correct=? WHERE id=? AND finished IS NULL',(now,int(correct),action_id))
    def report(self):
        with self.connect() as db:
            rows=db.execute('SELECT finished-started,wait_seconds,mandatory,critical,rare,correct FROM actions WHERE finished IS NOT NULL').fetchall()
        seconds=sum(r[0] for r in rows);waits=sorted(r[1] for r in rows)
        return {'completed':len(rows),'operator_seconds':seconds,
                'declared_correct_mandatory_per_minute':sum(r[2] and r[5] for r in rows)/(seconds/60) if seconds else None,
                'declared_correct_critical':sum(r[3] and r[5] for r in rows),
                'p90_wait_seconds':waits[max(0,math.ceil(.9*len(waits))-1)] if waits else None,
                'rare_served_share':sum(r[4] for r in rows)/len(rows) if rows else None,
                'quality_source':'operator_declared_development','independent_reference':False,'sales_impact':None}


def main():
    import argparse
    from goodsai.storage import output_lock,_atomic_text
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    r=sub.add_parser('rank')
    for name in ('input','policy','output','state'):r.add_argument('--'+name,type=Path,required=True)
    r.add_argument('--now',type=float,required=True);r.add_argument('--limit',type=int);r.add_argument('--demand',type=Path)
    b=sub.add_parser('begin');b.add_argument('--ranking',type=Path,required=True);b.add_argument('--task-id',required=True);b.add_argument('--actor',required=True)
    f=sub.add_parser('finish');f.add_argument('--action-id',type=int,required=True);f.add_argument('--correct',choices=['true','false'],required=True)
    sub.add_parser('report')
    for c in (b,f,sub.choices['report']):c.add_argument('--db',type=Path,required=True)
    args=p.parse_args()
    def read(path):return json.loads(path.read_text(encoding='utf-8'))
    if args.command=='rank':
        policy=RankPolicy(**read(args.policy));tasks=[ReviewTask(**row) for row in read(args.input)]
        with output_lock(args.state):
            state=read(args.state) if args.state.exists() else {'cursor':0,'policy_sha256':digest(asdict(policy))}
            if state['policy_sha256']!=digest(asdict(policy)):raise ValueError('Queue state policy mismatch')
            report=rank(tasks,policy,now=args.now,demand=read(args.demand) if args.demand else None,cursor=state['cursor'],limit=args.limit)
            args.output.parent.mkdir(parents=True,exist_ok=True)
            with args.output.open('x',encoding='utf-8') as stream:json.dump(report,stream,ensure_ascii=True,indent=2)
            with _atomic_text(args.state) as stream:json.dump({'cursor':report['next_cursor'],'policy_sha256':report['policy_sha256']},stream)
    elif args.command=='begin':
        row=next(r for r in read(args.ranking)['rows'] if r['task_id']==args.task_id)
        print(json.dumps({'action_id':QueueAudit(args.db).begin(row,args.actor)}))
    elif args.command=='finish':QueueAudit(args.db).finish(args.action_id,correct=args.correct=='true')
    else:print(json.dumps(QueueAudit(args.db).report()))


if __name__=='__main__':main()
