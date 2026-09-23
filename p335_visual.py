"""Optional control evidence and typed observations; never substitutes for XML."""
import hashlib
import math
import re
from datetime import datetime
from pathlib import Path

from p335_corpus import _sha


def _hash(value):
    if not isinstance(value,str) or not re.fullmatch('[0-9a-f]{64}',value): raise ValueError('INVALID_EVIDENCE_HASH')
    return value


def control_descriptor(source_sha256, descriptor=None):
    _hash(source_sha256)
    if descriptor is None:
        return {'schema':'hwpx-visual-control/v1','source_sha256':source_sha256,'status':'NOT_PROVIDED',
                'native_semantic_authority':False,'required_evidence':'Source-bound PDF bytes, renderer/version/route/time and page geometry.'}
    allowed={'source_sha256','control_sha256','renderer','renderer_version','creation_route','created_at','page_sizes_pt','notes'}
    if not isinstance(descriptor,dict) or set(descriptor)-allowed: raise ValueError('INVALID_CONTROL_FIELDS')
    if descriptor.get('source_sha256')!=source_sha256: raise ValueError('CONTROL_SOURCE_HASH_MISMATCH')
    _hash(descriptor.get('control_sha256'))
    for key in ('renderer','renderer_version','creation_route','created_at'):
        if not isinstance(descriptor.get(key),str) or not 0<len(descriptor[key])<=500: raise ValueError('MISSING_RENDER_PROVENANCE')
    if datetime.fromisoformat(descriptor['created_at'].replace('Z','+00:00')).tzinfo is None:
        raise ValueError('CONTROL_TIME_REQUIRES_TIMEZONE')
    pages=descriptor.get('page_sizes_pt')
    if not isinstance(pages,list) or not 1<=len(pages)<=200: raise ValueError('CONTROL_PAGE_LIMIT')
    if any(not isinstance(page,list) or len(page)!=2 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<v<=20_000 for v in page) for page in pages):
        raise ValueError('INVALID_PAGE_GEOMETRY')
    result={'schema':'hwpx-visual-control/v1',**descriptor,'page_count':len(pages),
            'status':'DECLARED_UNVERIFIED','native_semantic_authority':False,
            'authority':'VISUAL_CONTROL_METADATA_ONLY'}
    result['control_receipt_sha256']=_sha(result)
    return result


def inspect_pdf_control(path: Path, source_sha256: str, provenance: dict):
    """Offline adapter. PDF geometry observed here does not verify who rendered it."""
    if path.stat().st_size>20_000_000: raise ValueError('PDF_BYTES_LIMIT')
    raw=path.read_bytes()
    if not raw.startswith(b'%PDF-'): raise ValueError('INVALID_PDF_CONTROL')
    import fitz  # optional requirements-capture.txt; not a production hard dependency
    with fitz.open(stream=raw,filetype='pdf') as doc:
        if doc.is_encrypted or not 1<=len(doc)<=200: raise ValueError('UNSUPPORTED_PDF_CONTROL')
        sizes=[[page.rect.width,page.rect.height] for page in doc]
        descriptor=control_descriptor(source_sha256,{**provenance,'source_sha256':source_sha256,
            'control_sha256':hashlib.sha256(raw).hexdigest(),'page_sizes_pt':sizes})
        measurements=[]
        for index,page in enumerate(doc):
            blocks=page.get_text('blocks')
            area=page.rect.width*page.rect.height
            # Bounding rectangles can overlap: report a capped proxy, not true ink coverage.
            covered=sum(max(0,b[2]-b[0])*max(0,b[3]-b[1]) for b in blocks if len(b)>6 and b[6]==0)
            measurements.append({'page':index+1,'text_bbox_area_fraction_capped':min(1,covered/area),
                                 'text_block_count':len(blocks)})
    descriptor.pop('control_receipt_sha256',None)
    descriptor.update(status='PDF_BYTES_INSPECTED_RENDER_ROUTE_DECLARED',page_metrics=measurements,
                      measurement_method={'id':'pdf-text-bbox-proxy','version':'1','extractor':'PyMuPDF '+fitz.VersionBind,
                                          'limitation':'Not ink coverage, OCR, beauty, or native-open evidence.'})
    descriptor['control_receipt_sha256']=_sha(descriptor)
    return descriptor


def validate_annotation(source, annotation):
    allowed={'kind','evidence_type','value','method','control_sha256','note','pairwise_source_id','author'}
    if not isinstance(annotation,dict) or set(annotation)-allowed: raise ValueError('INVALID_ANNOTATION_FIELDS')
    if len(str(annotation))>8000: raise ValueError('ANNOTATION_LIMIT')
    evidence=annotation.get('evidence_type')
    if evidence not in {'NATIVE_XML','RENDER_CONTROL','HUMAN_NOTE','HEURISTIC'}: raise ValueError('INVALID_EVIDENCE_TYPE')
    kinds={'role_to_body_size_ratio','typographic_hierarchy','paragraph_rhythm','alignment_regularity',
           'whitespace_density','density','table_density_padding','caption_treatment','header_footer_restraint',
           'emphasis_frequency','script_mixing','line_length_proxy','diagram_table_integration','institutional_motif',
           'review','pairwise_visual_preference'}
    if annotation.get('kind') not in kinds: raise ValueError('INVALID_ANNOTATION_KIND')
    if evidence in {'NATIVE_XML','HEURISTIC'}:
        method=annotation.get('method') or {}
        if not all(k in method for k in ('id','version','parameters','applicability','confidence')):
            raise ValueError('METHOD_RECEIPT_REQUIRED')
        if not isinstance(method['confidence'],(int,float)) or not 0<=method['confidence']<=1:
            raise ValueError('INVALID_CONFIDENCE')
    if evidence=='RENDER_CONTROL':
        control=next((c for c in source['controls'] if c.get('control_sha256')==annotation.get('control_sha256')),None)
        if control is None: raise ValueError('ANNOTATION_REQUIRES_PAIRED_CONTROL')
        evidence_status=control['status']
    else: evidence_status='DECLARED'  # public API notes cannot self-certify measured XML
    result={**annotation,'source_id':source['source_id'],'source_sha256':source['sha256'],
            'evidence_status':evidence_status,'authority':'OBSERVATION_NOT_AESTHETIC_VERDICT'}
    result['annotation_sha256']=_sha(result)
    return result


def native_patterns(source):
    if not source.get('observations'): return []
    roles=source['observations']['roles']; body=next((r for r in roles if r['role']=='body'),None)
    observations=[]
    if body:
        base=body['authoring_preset']['run_format'].get('size')
        for r in roles:
            size=r['authoring_preset']['run_format'].get('size')
            if base and size:
                a=validate_annotation(source,{'kind':'role_to_body_size_ratio','evidence_type':'NATIVE_XML',
                    'value':{'role':r['role'],'ratio':size/base},
                    'method':{'id':'resolved-role-size-ratio','version':'1','parameters':{},
                              'applicability':'Dominant resolved sizes; mixed runs remain in source typography.','confidence':1}})
                a.pop('annotation_sha256');a['evidence_status']='COMPUTED_FROM_NATIVE_XML';a['annotation_sha256']=_sha(a)
                observations.append(a)
    return observations


def compare_controls(left, right):
    if not left or not right or left.get('status')=='NOT_PROVIDED' or right.get('status')=='NOT_PROVIDED':
        return {'status':'HOLD_MISSING_PAIRED_CONTROLS'}
    return {'status':'METADATA_COMPARISON_ONLY','left_control_sha256':left['control_sha256'],
            'right_control_sha256':right['control_sha256'],
            'page_count_equal':left['page_count']==right['page_count'],
            'page_sizes_equal':left['page_sizes_pt']==right['page_sizes_pt'],
            'renderer_route_equal':all(left[k]==right[k] for k in ('renderer','renderer_version','creation_route')),
            'native_semantic_authority':False,'visual_fidelity_verdict':'NOT_EVALUATED'}
