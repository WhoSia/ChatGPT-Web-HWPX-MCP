from __future__ import annotations
import copy
import tempfile
import unittest
from pathlib import Path
from hwpx import HwpxDocument
from p22_formatting import build_formatting_map, apply_formatting_atomic
from p334r2_package_validation import validate_hwpx_package_light
from p335_registry import intake_source, registry_snapshot, seal_source, validate_source_metadata
from p335_atlas import build_style_atlas, synthesize_templates, compile_template
from p335_visual import control_descriptor, validate_annotation, native_patterns, inspect_pdf_control, compare_controls
from scripts.verify_production_boundary import classify, verify


def metadata(source='a',institution='A'):
    return {'source_id':source,'original_filename':source+'.hwpx','institution':institution,
            'retrieved_at':'2026-09-23T00:00:00Z','access_status':'LOCALLY_GENERATED_NATIVE_EVIDENCE',
            'source_family':'test-fixture','provenance_notes':'Synthetic fixture; not a Hancom capture.'}


def fixture(root,source='a',institution='A',text='본문',size=10):
    path=root/(source+'.hwpx');doc=HwpxDocument.new();doc.add_paragraph(text);doc.save_to_path(path);doc.close()
    loc=next(p['locator'] for p in build_formatting_map(path)['paragraphs'] if p['direct_text_length'])
    apply_formatting_atomic(path,[{'op':'set_run_format','target':loc,'format':{'size':size}}],expected_revision=1,current_revision=1,validator=validate_hwpx_package_light)
    return intake_source(metadata(source,institution),path),path,loc


class RegistryAtlasTests(unittest.TestCase):
    def setUp(self): self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()

    def test_public_access_does_not_infer_open_rights(self):
        m=metadata();m.update(access_status='PUBLICLY_ACCESSIBLE',source_url='https://example.org/source')
        row=intake_source(m)
        self.assertEqual(row['reuse_status'],'UNKNOWN_REUSE_RIGHTS')
        self.assertEqual(row['exclusion_reason'],'BYTES_NOT_ACQUIRED')
        self.assertFalse(row['redistribution_authorized'])
        m['license_kind']='EXPLICIT_OPEN_LICENSE'
        with self.assertRaisesRegex(ValueError,'LICENSE_CLAIM'): intake_source(m)
        m.update(license_statement='CC BY 4.0',license_url='https://example.org/license')
        self.assertEqual(intake_source(m)['reuse_status'],'EXPLICIT_OPEN_LICENSE')

    def test_path_metadata_and_credential_urls_rejected(self):
        for update in ({'original_filename':'C:\\secret.hwpx'},{'path':'/private'}, {'source_url':'https://user:secret@example.org'}, {'retrieved_at':'2026-09-23'}):
            with self.subTest(update=update),self.assertRaises(ValueError): validate_source_metadata({**metadata(),**update})

    def test_receipts_deterministic_sorted_and_source_identity_preserved(self):
        a,p,_=fixture(self.root);b,_,_=fixture(self.root,'b','B','다른 본문')
        self.assertEqual(a,intake_source(metadata(),p))
        x=registry_snapshot([a,b]);y=registry_snapshot([b,a])
        self.assertEqual(x,y);self.assertEqual(a['institution'],'A')
        self.assertEqual(a['parser_status'],'PASS');self.assertNotIn(str(self.root),str(a))
        self.assertTrue(a['observations']['typography']['relative_size_by_script'])

    def test_duplicate_bytes_preserve_both_sources_but_one_vote(self):
        a,p,_=fixture(self.root);b=intake_source(metadata('b','B'),p)
        snap=registry_snapshot([a,b]);self.assertEqual(snap['exact_duplicates'],[['a','b']])
        atlas=build_style_atlas([a,b]);self.assertEqual(atlas['unique_documents'],1)
        self.assertEqual(len(atlas['source_index']),2)
        with self.assertRaisesRegex(ValueError,'DUPLICATE_SOURCE_ID'): registry_snapshot([a,a])

    def test_tampered_receipt_is_rejected(self):
        a,_,_=fixture(self.root);a['institution']='forged'
        with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'): build_style_atlas([a])

    def test_malformed_and_nonhwpx_are_excluded(self):
        p=self.root/'bad.hwpx';p.write_bytes(b'not a zip')
        row=intake_source(metadata(),p)
        self.assertEqual(row['package_status'],'REJECTED');self.assertEqual(row['inclusion_status'],'EXCLUDED')

    def test_document_volume_institution_and_minority_regimes(self):
        a,_,_=fixture(self.root,'a','A','가'*1000,10)
        b,_,_=fixture(self.root,'b','B','나',14)
        c,_,_=fixture(self.root,'c','B','다',14)
        atlas=build_style_atlas([a,b,c]);role=atlas['roles'][0]
        self.assertEqual(len(role['candidates']),2)
        small=next(c for c in role['candidates'] if c['documents']==2)
        self.assertAlmostEqual(small['document_share'],2/3,7)
        self.assertLess(small['volume_share'],.01)
        self.assertAlmostEqual(small['institution_balanced_share'],.5)
        self.assertGreater(role['document_distribution']['entropy_bits'],0)
        self.assertEqual(len(build_style_atlas([a,b,c],institution='A')['roles'][0]['candidates']),1)
        self.assertEqual(build_style_atlas([a,b,c],source_family='absent')['roles'],[])
        result=synthesize_templates([a,b,c],min_documents=1,min_share=.3)
        self.assertEqual(len(result['templates']),2)
        strict=synthesize_templates([a,b,c],min_documents=2,min_share=.7)
        self.assertEqual(strict['status'],'INSUFFICIENT_COMPATIBLE_SUPPORT')

    def test_explicit_template_compiles_and_applies_existing_atomic_primitives(self):
        a,_,_=fixture(self.root,'a',size=13.5)
        _,target,loc=fixture(self.root,'target',text='대상',size=9)
        template=synthesize_templates([a],mode='EXPLICIT_EXEMPLAR',source_id='a')['templates'][0]
        self.assertEqual(template['source_receipts'],{'a':a['source_receipt_sha256']})
        plan=compile_template(template,{'body':[loc]},expected_revision=1)
        self.assertTrue(all(op['op'] in {'set_run_format','set_paragraph_format'} for op in plan['operations']))
        apply_formatting_atomic(target,plan['operations'],expected_revision=1,current_revision=1,validator=validate_hwpx_package_light)
        style=next(p for p in build_formatting_map(target)['paragraphs'] if p['locator']==loc)['runs'][0]['style']
        self.assertEqual(style['size_pt'],13.5)
        before=target.read_bytes()
        with self.assertRaises(ValueError):
            apply_formatting_atomic(target,plan['operations'],expected_revision=1,current_revision=2,validator=validate_hwpx_package_light)
        self.assertEqual(before,target.read_bytes())

    def test_bundle_requires_cooccurrence_and_preserves_institution(self):
        a,_,_=fixture(self.root,'a','A');b,_,_=fixture(self.root,'b','B','둘')
        r=synthesize_templates([a,b],mode='COHERENT_BUNDLE',roles=['title','body'],min_documents=1)
        self.assertEqual(r['templates'],[])
        for source in (a,b):
            title=copy.deepcopy(source['observations']['roles'][0]);title['role']='title';title['authoring_preset']['run_format']['size']=18
            source['observations']['roles'].append(title)
        a=seal_source(a);b=seal_source(b)
        r=synthesize_templates([a,b],mode='COHERENT_BUNDLE',roles=['title','body'],min_documents=1)
        self.assertEqual(len(r['templates']),2)
        self.assertTrue(all(len(t['institutions'])==1 for t in r['templates']))
        self.assertEqual(synthesize_templates([a,b],mode='COHERENT_BUNDLE',roles=['title','body'],min_documents=2)['templates'],[])

    def test_readback_only_not_emitted_and_overlap_rejected(self):
        a,_,_=fixture(self.root)
        a['observations']['roles'][0]['authoring_preset']['run_format']['letter_spacing_by_script_readback_only']={'latin':3}
        a=seal_source(a);t=synthesize_templates([a],mode='EXPLICIT_EXEMPLAR',source_id='a')['templates'][0]
        plan=compile_template(t,{'body':['p0']},expected_revision=1)
        self.assertNotIn('letter_spacing_by_script_readback_only',str(plan))
        self.assertTrue(t['unresolved_dimensions'])
        with self.assertRaisesRegex(ValueError,'COLLISION'): compile_template(t,{'body':['p0','p0']},expected_revision=1)

    def test_exclusion_changes_corpus_hash_keeps_receipt(self):
        a,_,_=fixture(self.root);old=registry_snapshot([a]);a.update(inclusion_status='EXCLUDED',exclusion_reason='curator removal');a=seal_source(a)
        new=registry_snapshot([a]);self.assertNotEqual(new['corpus_sha256'],old['corpus_sha256']);self.assertEqual(len(new['records']),1)

    def test_visual_missing_declared_pair_and_wrong_binding(self):
        a,_,_=fixture(self.root)
        self.assertEqual(control_descriptor(a['sha256'])['status'],'NOT_PROVIDED')
        d={'source_sha256':a['sha256'],'control_sha256':'b'*64,'renderer':'Hancom','renderer_version':'declared 13',
           'creation_route':'manual export','created_at':'2026-09-23T00:00:00Z','page_sizes_pt':[[595,842]]}
        c=control_descriptor(a['sha256'],d);self.assertEqual(c['status'],'DECLARED_UNVERIFIED')
        self.assertFalse(c['native_semantic_authority'])
        with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'): control_descriptor('a'*64,d)
        self.assertEqual(compare_controls(c,None)['status'],'HOLD_MISSING_PAIRED_CONTROLS')
        self.assertEqual(compare_controls(c,c)['visual_fidelity_verdict'],'NOT_EVALUATED')

    def test_annotation_types_and_method_custody(self):
        a,_,_=fixture(self.root)
        with self.assertRaises(ValueError): validate_annotation(a,{'kind':'beauty','evidence_type':'AI_TRUTH'})
        with self.assertRaises(ValueError): validate_annotation(a,{'kind':'density','evidence_type':'HEURISTIC'})
        with self.assertRaises(ValueError): validate_annotation(a,{'kind':'density','evidence_type':'RENDER_CONTROL','control_sha256':'b'*64})
        n=validate_annotation(a,{'kind':'review','evidence_type':'HUMAN_NOTE','note':'Sparse heading treatment.'})
        self.assertEqual(n['evidence_status'],'DECLARED')
        self.assertEqual(native_patterns(a)[0]['evidence_status'],'COMPUTED_FROM_NATIVE_XML')

    def test_pdf_geometry_is_observed_but_renderer_not_certified(self):
        try: import fitz
        except ImportError: self.skipTest('optional capture dependency not installed')
        p=self.root/'control.pdf';doc=fitz.open();page=doc.new_page(width=595,height=842);page.insert_text((72,72),'Test');doc.save(p);doc.close()
        c=inspect_pdf_control(p,'a'*64,{'renderer':'fixture','renderer_version':'1','creation_route':'synthetic PDF','created_at':'2026-09-23T00:00:00Z'})
        self.assertEqual(c['page_count'],1);self.assertGreater(c['page_metrics'][0]['text_bbox_area_fraction_capped'],0)
        self.assertEqual(c['status'],'PDF_BYTES_INSPECTED_RENDER_ROUTE_DECLARED')


class ProductionBoundaryTests(unittest.TestCase):
    def test_failure_taxonomy_and_slow_bounded_polling(self):
        self.assertEqual(classify(429,None,'v'),'EXTERNAL_RATE_LIMIT')
        self.assertEqual(classify(503,None,'v'),'EXTERNAL_SERVICE_UNAVAILABLE')
        self.assertEqual(classify(200,{'version':'old'},'v'),'PRODUCTION_VERSION_STALE')
        self.assertEqual(classify(200,None,'v'),'MALFORMED_HEALTH_RESPONSE')
        delays=[];calls=[]
        def fetch(url,post=False): calls.append(url);return 429,None,'60'
        result=verify('https://example.org','v',None,fetch=fetch,sleep=delays.append)
        self.assertFalse(result['ok']);self.assertEqual(len(calls),8);self.assertEqual(delays,[60]*7)

    def test_exact_head_required(self):
        healthy={'version':'v','release_commit':'a','oauth':{'durable_store_reachable':True},'documents':{'durable_store_reachable':True}}
        self.assertEqual(classify(200,healthy,'v','b'),'PRODUCTION_VERSION_STALE')
        self.assertEqual(classify(200,healthy,'v','a'),'READY')


if __name__=='__main__': unittest.main()
