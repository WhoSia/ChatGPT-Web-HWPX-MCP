import os
import secrets
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from document_store import DurableDocumentStore
from p335_registry import PostgresCorpusRegistry, intake_source, seal_source
from p335_mcp import register_corpus_tools
from test_p335_registry_atlas import metadata, fixture


@unittest.skipUnless(os.environ.get('P12_AUTH_DATABASE_URL'),'Postgres integration requires test database')
class CorpusStoreTests(unittest.TestCase):
    def setUp(self):
        self.store=DurableDocumentStore(os.environ['P12_AUTH_DATABASE_URL'],os.environ['P12_STATE_SECRET'])
        self.registry=PostgresCorpusRegistry(self.store);self.owner='r4-test-'+secrets.token_hex(10)
    def tearDown(self):
        with self.store._connect() as conn:
            conn.execute('DELETE FROM hwpx_corpus_receipts WHERE owner_subject=%s',(self.owner,))

    def test_restart_encryption_owner_isolation_history_and_cas(self):
        row=intake_source(metadata());r=self.registry.append(self.owner,row)
        self.assertEqual(r['revision'],1)
        reloaded=PostgresCorpusRegistry(self.store)
        self.assertEqual(reloaded.get(self.owner,'a'),row)
        self.assertEqual(reloaded.records('different-owner'),[])
        with self.assertRaisesRegex(ValueError,'NOT_FOUND'): reloaded.get('different-owner','a')
        with self.store._connect() as conn:
            raw=bytes(conn.execute('SELECT encrypted_payload FROM hwpx_corpus_receipts WHERE owner_subject=%s',(self.owner,)).fetchone()[0])
        self.assertNotIn(b'provenance_notes',raw)
        self.assertTrue(reloaded.append(self.owner,row)['idempotent'])
        changed=seal_source({**row,'exclusion_reason':'manual exclusion'})
        with self.assertRaisesRegex(ValueError,'CAS'): reloaded.append(self.owner,changed)
        self.assertEqual(reloaded.append(self.owner,changed,row['source_receipt_sha256'])['revision'],2)
        self.assertEqual(reloaded.get(self.owner,'a',1),row)

    def test_concurrent_updates_have_one_winner(self):
        row=intake_source(metadata());self.registry.append(self.owner,row)
        def race(reason):
            try:
                self.registry.append(self.owner,seal_source({**row,'exclusion_reason':reason}),row['source_receipt_sha256']);return 'won'
            except ValueError: return 'conflict'
        with ThreadPoolExecutor(2) as pool: results=list(pool.map(race,['left','right']))
        self.assertCountEqual(results,['won','conflict'])

    def test_mcp_intake_synthesis_stale_gate_paging_and_owner_checks(self):
        functions={}
        class MCP:
            def tool(self):
                def register(fn): functions[fn.__name__]=fn;return fn
                return register
        with tempfile.TemporaryDirectory() as tmp:
            row,path,loc=fixture(Path(tmp));doc_id='doc_'+secrets.token_urlsafe(18)
            docmeta={'owner_subject':self.owner,'revision':1,'filename':'fixture.hwpx','document_id':doc_id}
            self.store.put_revision(document_id=doc_id,owner_subject=self.owner,revision=1,expected_revision=0,
                                    metadata=docmeta,data=path.read_bytes(),expires_at_epoch=4102444800)
            try:
                def owned(document_id):
                    if document_id!=doc_id: raise PermissionError('Not owned')
                    return docmeta,path
                core=SimpleNamespace(mcp=MCP(),DOCUMENT_STORE=self.store,_caller_subject=lambda:self.owner)
                register_corpus_tools(core,owned)
                with self.assertRaises(PermissionError): functions['register_corpus_source'](metadata(),'someone-elses-document')
                result=functions['register_corpus_source'](metadata(),doc_id)
                self.assertEqual(result['source']['document_revision'],1)
                self.assertNotIn('observations',result['source'])
                selection={'mode':'EXPLICIT_EXEMPLAR','source_id':'a'}
                result=functions['synthesize_corpus_templates'](**selection)
                template=result['items'][0]
                plan=functions['plan_corpus_template_transfer'](doc_id,template['template_sha256'],result['source_corpus_sha256'],{'body':[loc]},selection)
                self.assertEqual(plan['expected_revision'],1)
                with self.assertRaisesRegex(ValueError,'STALE'): functions['plan_corpus_template_transfer'](doc_id,template['template_sha256'],'a'*64,{'body':[loc]},selection)
                with self.assertRaises(ValueError): functions['query_corpus_registry'](limit=21)
                source=functions['get_corpus_source']('a')['source']
                functions['set_corpus_inclusion']('a',False,'curator exclusion',source['source_receipt_sha256'])
                self.assertEqual(functions['query_corpus_registry'](inclusion_status='EXCLUDED')['total'],1)
            finally: self.store.delete_document(doc_id)


if __name__=='__main__': unittest.main()
