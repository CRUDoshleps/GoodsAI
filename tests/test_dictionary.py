from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import sqlite3
import tempfile
import unittest
from fastapi.testclient import TestClient

from goodsai.contracts import load_config,Product
from goodsai.dictionary import DictionaryStore,VersionConflict
from goodsai.dictionary_app import create_app,HTML
from goodsai.verify import Extractor

ACCOUNTS={
 'proposer-token-0001':{'name':'author','role':'proposer'},
 'reviewer-token-0001':{'name':'reviewer','role':'reviewer'},
 'owner-token-0000001':{'name':'owner','role':'owner'},
 'reader-token-000001':{'name':'reader','role':'reader'},
}


class DictionaryTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.folder=Path(temp.name);self.store=DictionaryStore(self.folder/'dictionary.sqlite',load_config())
        self.base=self.store.current()['id']
        self.products=[Product('synthetic-1','761','Смартфон Самсунг QX-900 8/256GB черный',None,('synthetic',)),
                       Product('synthetic-2','482','Чайник Polaris KT-1 1.7 л черный',None,('synthetic',))]
    def draft(self,**changes):
        values=dict(base=self.base,author='author',attribute='brand',canonical='Samsung',alias='Самсунг',
                    categories=['482','761'],provenance={'kind':'manual','reference':'synthetic review'})
        return self.store.draft(**(values|changes))
    def reviewed(self,**changes):
        p=self.draft(**changes);p=self.store.impact(p['id'],p['revision'],self.products)
        return self.store.review(p['id'],p['revision'],'reviewer')

    def test_draft_impact_review_publish_and_rollback_preserve_previous_versions_and_raw_source(self):
        raw=deepcopy(self.products);initial=self.store.current()
        p=self.draft();self.assertEqual(self.store.current()['id'],self.base)
        p=self.store.impact(p['id'],p['revision'],self.products)
        self.assertTrue(p['impact']['changes']);self.assertIsNone(p['impact']['metrics']['delta_tp'])
        self.assertEqual(self.products,raw)
        p=self.store.review(p['id'],p['revision'],'reviewer')
        published=self.store.publish(p['id'],p['revision'],self.base,'owner')
        self.assertNotEqual(published['id'],self.base);self.assertEqual(published['publisher'],'owner')
        self.assertIn('Самсунг',published['config']['brands']['Samsung'])
        self.assertEqual(self.store.version(self.base),initial)
        back=self.store.rollback(self.base,published['id'],'owner')
        self.assertNotEqual(back['id'],self.base);self.assertEqual(back['config']['brands'],initial['config']['brands'])
        self.assertEqual(self.store.version(published['id'])['config'],published['config'])
        with self.store.connect() as db:
            with self.assertRaises(sqlite3.IntegrityError):db.execute('DELETE FROM versions WHERE id=?',(self.base,))

    def test_twenty_synthetic_proposals_validate_collisions_scope_cycles_types_and_unknowns(self):
        cases=[({},True),({'canonical':'Polaris','alias':'Поларис'},True),
               ({'canonical':'Midea','alias':'Мидеа'},True),({'canonical':'Apple','alias':'iPhone'},False),
               ({'canonical':'Apple','alias':'Samsung'},False),({'canonical':'Samsung','alias':'Apple'},False),
               ({'canonical':'Zorion','alias':'Зорион'},False),({'attribute':'power_w','canonical':'2100','alias':'2.1 кВт'},False),
               ({'categories':['761']},False),({'categories':['999']},False),
               ({'alias':'Galaxy'},False),({'alias':'Samsung'},False),
               ({'canonical':'Samsung','alias':'Самсунг Ultra'},False),({'canonical':'Apple','alias':'Android'},False),
               ({'canonical':'Nokia','alias':'Нокиа'},True),({'canonical':'Polaris','alias':'Полярис'},False),
               ({'canonical':'Xiaomi','alias':'Redmi'},False),({'canonical':'Bosch','alias':'Samsung'},False),
               ({'attribute':'ram_gb'},False),({'canonical':'Samsung','alias':'<script>bad</script>'},False)]
        self.assertEqual(len(cases),20)
        for changes,valid in cases:
            with self.subTest(changes=changes):
                p=self.draft(**changes)
                if valid:self.assertIn(p['payload']['alias'],self.store.candidate(p)['brands'][p['payload']['canonical']])
                else:
                    with self.assertRaises(ValueError):self.store.candidate(p)
        self.assertEqual(len(self.store.proposals()),20)
        self.assertEqual(self.store.current()['id'],self.base)

    def test_publish_is_compare_and_swap_and_does_not_overwrite_another_owner(self):
        first=self.reviewed();second=self.reviewed(canonical='Polaris',alias='Поларис')
        def publish(p):
            try:return self.store.publish(p['id'],p['revision'],self.base,'owner')['id']
            except VersionConflict:return None
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(publish,[first,second]))
        self.assertEqual(sum(v is not None for v in results),1)
        with self.assertRaises(VersionConflict):self.store.rollback(self.base,self.base,'owner')

    def test_review_and_impact_data_guards(self):
        p=self.draft()
        with self.assertRaises(ValueError):self.store.review(p['id'],0,'reviewer')
        with self.assertRaises(ValueError):self.store.impact(p['id'],0,[Product('test','761','test',source_flags=('test_reserved',))])
        p=self.store.impact(p['id'],0,self.products)
        with self.assertRaises(ValueError):self.store.review(p['id'],p['revision'],'author')
        p=self.store.review(p['id'],p['revision'],'reviewer')
        with self.assertRaises(ValueError):self.store.publish(p['id'],p['revision'],self.base,'author')
        with self.assertRaises(ValueError):self.draft(provenance={'kind':'model_output','reference':'AI'})

    def test_http_roles_full_workflow_and_no_untrusted_html_execution(self):
        with TestClient(create_app(self.store,ACCOUNTS,self.products)) as client:
            self.assertEqual(client.get('/dictionary/state').status_code,401)
            self.assertEqual(client.get('/dictionary/state',headers={b'Authorization':'Bearer ключ'.encode('utf-8')}).status_code,401)
            def call(path,body,token='proposer-token-0001'):
                return client.post('/dictionary/'+path,json=body,headers={'Authorization':'Bearer '+token})
            draft=dict(base=self.base,attribute='brand',canonical='Samsung',alias='Самсунг',categories=['482','761'],
                       provenance={'kind':'manual','reference':'<script>alert(1)</script>'})
            self.assertEqual(call('proposals',draft,'reader-token-000001').status_code,403)
            p=call('proposals',draft).json()
            p=call(f"proposals/{p['id']}/impact",{'revision':p['revision']}).json()
            self.assertEqual(call(f"proposals/{p['id']}/review",{'revision':p['revision']}).status_code,403)
            p=call(f"proposals/{p['id']}/review",{'revision':p['revision']},'reviewer-token-0001').json()
            self.assertEqual(call(f"proposals/{p['id']}/publish",{'revision':p['revision'],'expected_version':self.base},'reviewer-token-0001').status_code,403)
            published=call(f"proposals/{p['id']}/publish",{'revision':p['revision'],'expected_version':self.base},'owner-token-0000001')
            self.assertEqual(published.status_code,200)
            stale=call('rollback',{'target':self.base,'expected_version':self.base},'owner-token-0000001')
            self.assertEqual(stale.status_code,409)
            html=client.get('/')
            self.assertIn('sha256-',html.headers['Content-Security-Policy'])
            self.assertNotIn('innerHTML',HTML);self.assertIn('textContent',HTML)
            self.assertEqual(html.headers['Cache-Control'],'no-store')


if __name__=='__main__':unittest.main()
