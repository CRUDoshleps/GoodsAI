"""Human-reviewed immutable versions of the existing config dictionaries, not a new registry."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time
import unicodedata
import uuid

from goodsai.config import validate_config
from goodsai.verify import Extractor


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def literal(value,maximum=128):
    if (not isinstance(value,str) or not value.strip() or value!=value.strip() or len(value)>maximum
            or any(ord(c)<32 for c in value)):raise ValueError('Invalid dictionary text')
    return value


def translit(value):
    mapping=dict(zip('абвгдеёжзийклмнопрстуфхцчшщъыьэюя',
                     ['a','b','v','g','d','e','e','zh','z','i','y','k','l','m','n','o','p','r','s','t','u','f','kh','ts','ch','sh','shch','','y','','e','yu','ya']))
    value=''.join(mapping.get(c,c) for c in value.casefold())
    return ''.join(c for c in unicodedata.normalize('NFKD',value) if c.isalnum())


class VersionConflict(ValueError):pass


class DictionaryStore:
    def __init__(self,path,config,*,semantic_pairs=()):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.semantic_pairs=frozenset(tuple(pair) for pair in semantic_pairs)
        config=validate_config(config)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS versions(id TEXT PRIMARY KEY, parent TEXT, config TEXT NOT NULL,
                    config_hash TEXT NOT NULL, author TEXT NOT NULL, reviewer TEXT NOT NULL, created REAL NOT NULL,
                    action TEXT NOT NULL, publisher TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS current(singleton INTEGER PRIMARY KEY CHECK(singleton=1), version TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY, base TEXT NOT NULL, author TEXT NOT NULL,
                    payload TEXT NOT NULL, status TEXT NOT NULL, revision INTEGER NOT NULL, reviewer TEXT, impact TEXT, published TEXT);
                CREATE TRIGGER IF NOT EXISTS immutable_version_update BEFORE UPDATE ON versions BEGIN SELECT RAISE(ABORT,'immutable version'); END;
                CREATE TRIGGER IF NOT EXISTS immutable_version_delete BEFORE DELETE ON versions BEGIN SELECT RAISE(ABORT,'immutable version'); END;
            ''')
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT version FROM current').fetchone() is None:
                version=self._version(db,config,None,'bootstrap','bootstrap','bootstrap')
                db.execute('INSERT INTO current VALUES(1,?)',(version,))

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def _version(self,db,config,parent,author,reviewer,action,publisher=None):
        now=time.time();config=validate_config(config);config_hash=digest(config);publisher=publisher or reviewer
        version=digest([parent,config_hash,author,reviewer,publisher,now,action])
        db.execute('INSERT INTO versions VALUES(?,?,?,?,?,?,?,?,?)',
                   (version,parent,json.dumps(config,ensure_ascii=True),config_hash,author,reviewer,now,action,publisher))
        return version

    def current(self):
        with self.connect() as db:
            row=db.execute('SELECT v.* FROM versions v JOIN current c ON v.id=c.version').fetchone()
        return self._decode_version(row)

    @staticmethod
    def _decode_version(row):
        if row is None:raise ValueError('Unknown dictionary version')
        record=dict(row);record['config']=json.loads(record['config']);return record

    def version(self,version):
        with self.connect() as db:return self._decode_version(db.execute('SELECT * FROM versions WHERE id=?',(version,)).fetchone())

    def _proposal(self,db,proposal):
        row=db.execute('SELECT * FROM proposals WHERE id=?',(proposal,)).fetchone()
        if row is None:raise ValueError('Unknown proposal')
        value=dict(row);value['payload']=json.loads(value['payload']);value['impact']=json.loads(value['impact']) if value['impact'] else None
        return value

    def proposals(self):
        with self.connect() as db:return [self._proposal(db,row[0]) for row in db.execute('SELECT id FROM proposals ORDER BY rowid DESC')]

    def draft(self,*,base,author,attribute,canonical,alias,categories,provenance):
        literal(author);literal(attribute);literal(canonical);literal(alias)
        if not isinstance(categories,list) or len(set(categories))!=len(categories) or any(not isinstance(v,str) for v in categories):
            raise ValueError('Invalid category scope')
        if (not isinstance(provenance,dict) or set(provenance)!={'kind','reference'}
                or provenance['kind'] not in {'manual','confirmed_feedback'}):raise ValueError('Provenance must be manual or confirmed feedback')
        literal(provenance['reference'],256)
        payload=dict(attribute=attribute,canonical=canonical,alias=alias,categories=sorted(categories),provenance=provenance)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT version FROM current').fetchone()[0]!=base:raise VersionConflict('Stale dictionary version')
            proposal=uuid.uuid4().hex
            db.execute('INSERT INTO proposals(id,base,author,payload,status,revision) VALUES(?,?,?,?,?,0)',
                       (proposal,base,author,json.dumps(payload,ensure_ascii=True),'draft'))
            return self._proposal(db,proposal)

    def candidate(self,proposal):
        config=deepcopy(self.version(proposal['base'])['config']);p=proposal['payload'];attr=p['attribute']
        if attr not in {'brand','color'}:raise ValueError('Only existing brand/color alias dictionaries support this operation; numeric/catalog schemas require schema review')
        affected=sorted(cat for cat,attrs in config['categories'].items() if attr in attrs)
        if p['categories']!=affected:raise ValueError('Global alias scope must explicitly include every affected category')
        table=config['brands' if attr=='brand' else 'colors'];canonical=p['canonical'];alias=p['alias']
        if canonical not in table:raise ValueError('Unknown canonical value remains a proposal; schema owner must approve its vocabulary separately')
        for owner,spellings in table.items():
            if alias.casefold() in {v.casefold() for v in [owner,*spellings]}:
                if owner!=canonical:raise ValueError('Alias collision/cycle with another canonical value')
                raise ValueError('Alias already exists; no change')
        if (translit(alias)!=translit(canonical)
                and (attr,canonical,alias) not in self.semantic_pairs):
            raise ValueError('Alias is not a literal/transliteration equivalent; an explicit semantic policy is required')
        # No canonical-to-canonical edges, category inference, units or source rewriting.
        table[canonical].append(alias)
        config['dictionary_version']='dictionary-'+digest([proposal['id'],proposal['base']])[:24]
        return validate_config(config)

    def impact(self,proposal_id,revision,products,*,reference=None):
        with self.connect() as db:proposal=self._proposal(db,proposal_id)
        if proposal['revision']!=revision or proposal['status']!='draft':raise VersionConflict('Stale proposal revision')
        products=tuple(products)
        if not products:raise ValueError('An approved development stream is required for impact')
        for p in products:
            flags=set(p.source_flags)
            if not flags&{'synthetic','development','validation_feedback'} or flags&{'test_reserved','closed_test','exposed_test'}:
                raise ValueError('Impact accepts approved development/synthetic source only')
        old=self.version(proposal['base'])['config'];new=self.candidate(proposal)
        before=[Extractor(old).predict(p,'dictionary-impact') for p in products]
        after=[Extractor(new).predict(p,'dictionary-impact') for p in products]
        changes=[]
        for p,b,a in zip(products,before,after):
            for previous,current in zip(b['attributes'],a['attributes']):
                if previous!=current:
                    changes.append({'sku_id':p.sku_id,'attribute':current['attribute'],
                                    'before':previous,'after':current})
        metrics={'before':None,'after':None,'delta_tp':None,'delta_fp':None,'delta_fn':None,'status':'reviewed_labels_required'}
        reference_hash=None
        if reference is not None:
            from goodsai.evaluate import evaluate
            import tempfile
            reference=Path(reference);reference_hash=hashlib.sha256(reference.read_bytes()).hexdigest()
            # Reference must name only these development inputs and retain explicit manual review provenance.
            labels=[json.loads(line) for line in reference.read_text(encoding='utf-8').splitlines() if line.strip()]
            by_sku={p.sku_id:p for p in products}
            if (len({r['sku_id'] for r in labels})!=len(labels) or any(r['sku_id'] not in by_sku for r in labels)
                    or any(r.get('source')!='manual' or r.get('annotation_status')!='reviewed' for r in labels)):
                raise ValueError('Impact reference must be reviewed development matching the input')
            for row in labels:
                p=by_sku[row['sku_id']]
                if (row.get('title'),row.get('description'))!=(p.title,p.description):raise ValueError('Reference/source mismatch')
            with tempfile.TemporaryDirectory() as folder:
                reports=[]
                for name,rows,config in (('before',before,old),('after',after,new)):
                    path=Path(folder)/(name+'.jsonl');path.write_text(''.join(json.dumps(r,ensure_ascii=True)+'\n' for r in rows),encoding='utf-8')
                    reports.append(evaluate(path,reference,config))
            metrics.update(before=reports[0],after=reports[1],status='reviewed_development')
            for key in ('tp','fp','fn'):
                metrics['delta_'+key]=reports[1].get('metrics',{}).get('micro',{}).get(key,0)-reports[0].get('metrics',{}).get('micro',{}).get(key,0)
        report={'base_version':proposal['base'],'proposal_id':proposal_id,'candidate_config_sha256':digest(new),
                'source_sha256':digest([p.as_dict() for p in products]),'reference_sha256':reference_hash,
                'cards':len(products),'changes':changes,'metrics':metrics,'raw_source_modified':False,
                'diff':{'attribute':proposal['payload']['attribute'],'canonical':proposal['payload']['canonical'],
                        'added_alias':proposal['payload']['alias'],'categories':proposal['payload']['categories']},
                'independent_reference':False}
        with self.connect() as db:
            changed=db.execute('UPDATE proposals SET impact=?,revision=revision+1 WHERE id=? AND revision=? AND status=?',
                               (json.dumps(report,ensure_ascii=True),proposal_id,revision,'draft')).rowcount
            if changed!=1:raise VersionConflict('Proposal changed during impact')
            return self._proposal(db,proposal_id)

    def review(self,proposal_id,revision,reviewer):
        literal(reviewer)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');p=self._proposal(db,proposal_id)
            if p['revision']!=revision or p['status']!='draft':raise VersionConflict('Stale proposal revision')
            if p['author']==reviewer:raise ValueError('A different reviewer is required')
            if not p['impact'] or p['impact']['candidate_config_sha256']!=digest(self.candidate(p)):
                raise ValueError('A current reproducible impact report is required')
            db.execute('UPDATE proposals SET reviewer=?,status=?,revision=revision+1 WHERE id=?',(reviewer,'review',proposal_id))
            return self._proposal(db,proposal_id)

    def publish(self,proposal_id,revision,expected_version,owner):
        literal(owner)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');p=self._proposal(db,proposal_id)
            current=db.execute('SELECT version FROM current').fetchone()[0]
            if current!=expected_version or p['base']!=current or p['revision']!=revision:raise VersionConflict('Dictionary/proposal version changed')
            if p['status']!='review' or not p['reviewer'] or owner==p['author']:raise ValueError('Reviewed proposal and independent schema owner approval required')
            candidate=self.candidate(p)
            if not p['impact'] or p['impact']['candidate_config_sha256']!=digest(candidate):raise ValueError('Impact mismatch')
            version=self._version(db,candidate,current,p['author'],p['reviewer'],'publish:'+proposal_id,owner)
            db.execute('UPDATE current SET version=? WHERE singleton=1',(version,))
            db.execute('UPDATE proposals SET status=?,published=?,revision=revision+1 WHERE id=?',('published',version,proposal_id))
            return self._decode_version(db.execute('SELECT * FROM versions WHERE id=?',(version,)).fetchone())

    def rollback(self,target,expected_version,owner):
        literal(owner);config=deepcopy(self.version(target)['config'])
        config['dictionary_version']='rollback-'+uuid.uuid4().hex[:24]
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current=db.execute('SELECT version FROM current').fetchone()[0]
            if current!=expected_version:raise VersionConflict('Dictionary version changed')
            version=self._version(db,config,current,owner,'approved-version:'+target,'rollback:'+target,owner)
            db.execute('UPDATE current SET version=? WHERE singleton=1',(version,))
            return self._decode_version(db.execute('SELECT * FROM versions WHERE id=?',(version,)).fetchone())
