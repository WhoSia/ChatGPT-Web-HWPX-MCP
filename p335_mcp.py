"""R4 MCP surface; all paths and owner identities come from trusted custody."""
import tempfile
from pathlib import Path
from p335_registry import PostgresCorpusRegistry, intake_source, registry_snapshot, seal_source
from p335_atlas import build_style_atlas, synthesize_templates, compile_template
from p335_visual import control_descriptor, validate_annotation, native_patterns, compare_controls


def register_corpus_tools(core, owned_document):
    registry=PostgresCorpusRegistry(core.DOCUMENT_STORE)

    def owner(): return core._caller_subject()
    def summary(row): return {k:v for k,v in row.items() if k not in {'observations','annotations'}}
    def page(rows,offset,limit):
        if not 1<=limit<=20 or offset<0: raise ValueError('INVALID_PAGE_BOUNDS')
        return {'total':len(rows),'items':rows[offset:offset+limit],
                'next_offset':offset+limit if offset+limit<len(rows) else None}

    @core.mcp.tool()
    def get_corpus_registry_contract() -> dict:
        """Describe corpus intake fields, evidence boundaries, bounds and transfer workflow."""
        owner()
        return {'ok':True,'phase':'P3.35-R4','schema':'hwpx-corpus-source/v1',
                'required_metadata':['source_id','original_filename','institution','retrieved_at','access_status'],
                'optional_metadata':['title','source_family','source_url','license_kind','license_statement','license_url','provenance_notes','native_status'],
                'access_status':['PUBLICLY_ACCESSIBLE','LOCALLY_GENERATED_NATIVE_EVIDENCE','USER_PROVIDED_RESEARCH_EVIDENCE','UNVERIFIED'],
                'license_kind':['UNKNOWN','EXPLICIT_OPEN_LICENSE','RESTRICTED'],
                'bounds':{'sources_per_owner':500,'page_size':20,'controls_per_source':10,'annotations_per_source':100},
                'input_policy':'Owned document revision or metadata only; URLs are provenance, never fetched.',
                'authority':'EVIDENCE_GUIDED_TEMPLATE_CANDIDATE',
                'workflow':['register_corpus_source','query_style_atlas','synthesize_corpus_templates','plan_corpus_template_transfer','apply_formatting','deliver_document'],
                'gates':{'native_render':'REQUIRES_DIRECT_EVIDENCE','visual_control':'DECLARED_METADATA_IS_NOT_INSPECTED_BYTES','readback_only':'NOT_EMITTED_AS_MUTATIONS'}}

    @core.mcp.tool()
    def register_corpus_source(metadata: dict, document_id: str = '', expected_receipt: str = '') -> dict:
        """Register provenance and immutable owned HWPX revision; no URL fetching or redistribution.

        Without document_id, creates an excluded metadata-only record. Updates
        require the prior source_receipt_sha256; identical intake is idempotent.
        """
        subject=owner()
        if document_id:
            meta,_=owned_document(document_id)
            snapshot=core.DOCUMENT_STORE.load_revision(document_id,int(meta['revision']))
            if snapshot is None: raise ValueError('SOURCE_REVISION_NOT_AVAILABLE')
            if snapshot['owner_subject'] != subject: raise PermissionError('SOURCE_NOT_OWNED')
            with tempfile.TemporaryDirectory(prefix='hwpx-corpus-') as tmp:
                path=Path(tmp)/'source.hwpx';path.write_bytes(snapshot['bytes'])
                row=intake_source(metadata,path,document_id=document_id,revision=int(meta['revision']))
        else: row=intake_source(metadata)
        row['annotations']=native_patterns(row);row=seal_source(row)
        receipt=registry.append(subject,row,expected_receipt or None)
        return {'ok':True,**receipt,'source':summary(row)}

    @core.mcp.tool()
    def get_corpus_source(source_id: str, revision: int | None = None, include_observations: bool = False) -> dict:
        """Read an owner-scoped source receipt, optionally its cached native distributions."""
        row=registry.get(owner(),source_id,revision)
        return {'ok':True,'source':row if include_observations else summary(row)}

    @core.mcp.tool()
    def query_corpus_registry(institution: str = '', source_family: str = '', inclusion_status: str = '', offset: int = 0, limit: int = 20) -> dict:
        """Bounded receipt listing with coverage, hash and exact/style-similarity groups."""
        snap=registry_snapshot(registry.records(owner()))
        rows=[summary(r) for r in snap['records'] if (not institution or r['institution']==institution)
              and (not source_family or r['source_family']==source_family)
              and (not inclusion_status or r['inclusion_status']==inclusion_status)]
        return {'ok':True,**{k:v for k,v in snap.items() if k!='records'},**page(rows,offset,limit)}

    @core.mcp.tool()
    def set_corpus_inclusion(source_id: str, included: bool, reason: str, expected_receipt: str) -> dict:
        """Append an inclusion decision; historical provenance is retained under receipt CAS."""
        subject=owner();row=registry.get(subject,source_id)
        if not reason.strip() or len(reason)>1000: raise ValueError('INCLUSION_REASON_REQUIRED')
        if included and (row['parser_status']!='PASS' or row['role_status']!='PASS'):
            raise ValueError('SOURCE_NOT_ELIGIBLE')
        row.update(inclusion_status='INCLUDED' if included else 'EXCLUDED',exclusion_reason=None if included else reason,
                   inclusion_decision_note=reason)
        row=seal_source(row)
        return {'ok':True,**registry.append(subject,row,expected_receipt),'source':summary(row)}

    @core.mcp.tool()
    def pair_corpus_visual_control(source_id: str, descriptor: dict, expected_receipt: str) -> dict:
        """Pair source-bound PDF metadata as DECLARED_UNVERIFIED; never claim native rendering."""
        subject=owner();row=registry.get(subject,source_id)
        control=control_descriptor(row['sha256'],descriptor)
        if len(row['controls'])>=10: raise ValueError('CONTROL_COUNT_LIMIT')
        row['controls'].append(control);row=seal_source(row)
        return {'ok':True,**registry.append(subject,row,expected_receipt),'control':control,'source_receipt_sha256':row['source_receipt_sha256']}

    @core.mcp.tool()
    def annotate_corpus_source(source_id: str, annotation: dict, expected_receipt: str) -> dict:
        """Append evidence-typed note; heuristics require method/version/applicability/confidence."""
        subject=owner();row=registry.get(subject,source_id)
        note=validate_annotation(row,annotation)
        if len(row['annotations'])>=100: raise ValueError('ANNOTATION_COUNT_LIMIT')
        if annotation.get('pairwise_source_id'): registry.get(subject,annotation['pairwise_source_id'])
        row['annotations'].append(note);row=seal_source(row)
        return {'ok':True,**registry.append(subject,row,expected_receipt),'annotation':note,'source_receipt_sha256':row['source_receipt_sha256']}

    @core.mcp.tool()
    def compare_corpus_visual_controls(left_source_id: str, right_source_id: str) -> dict:
        """Compare latest declared PDF controls without claiming visual or native equivalence."""
        subject=owner();left=registry.get(subject,left_source_id);right=registry.get(subject,right_source_id)
        return {'ok':True,**compare_controls(next(iter(left['controls'][-1:]),None),next(iter(right['controls'][-1:]),None))}

    @core.mcp.tool()
    def query_style_atlas(institution: str = '', role: str = '', source_family: str = '', dimension: str = '', offset: int = 0, limit: int = 20) -> dict:
        """Query document/volume/institution-balanced regimes with provenance and minority alternatives."""
        atlas=build_style_atlas(registry.records(owner()),institution=institution or None,role=role or None,
                                source_family=source_family or None,dimension=dimension or None)
        candidates=[{'role':r['role'],**c} for r in atlas['roles'] for c in r['candidates']]
        return {'ok':True,**{k:v for k,v in atlas.items() if k not in {'roles','source_index'}},
                'role_summaries':[{k:v for k,v in r.items() if k!='candidates'} for r in atlas['roles']],
                **page(candidates,offset,limit)}

    @core.mcp.tool()
    def synthesize_corpus_templates(mode: str = 'CORPUS_SUPPORTED', source_id: str = '', roles: list[str] | None = None,
                                   institution: str = '', min_documents: int = 2, min_share: float = 0.5,
                                   offset: int = 0, limit: int = 20) -> dict:
        """Return explicit, supported-role or co-occurring institutional bundle candidates."""
        result=synthesize_templates(registry.records(owner()),mode=mode,source_id=source_id or None,roles=roles,
                                    institution=institution or None,min_documents=min_documents,min_share=min_share)
        return {'ok':True,**{k:v for k,v in result.items() if k!='templates'},**page(result['templates'],offset,limit)}

    @core.mcp.tool()
    def plan_corpus_template_transfer(target_document_id: str, template_sha256: str, source_corpus_sha256: str,
                                     targets_by_role: dict, selection: dict) -> dict:
        """Recompute sealed template from current registry, reject stale evidence, emit existing CAS operations.

        selection uses synthesize_corpus_templates mode/source_id/roles/institution/min_documents/min_share.
        Apply returned operations with apply_formatting and its expected_revision.
        """
        subject=owner();meta,_=owned_document(target_document_id)
        if set(selection)-{'mode','source_id','roles','institution','min_documents','min_share'}: raise ValueError('INVALID_SELECTION_FIELDS')
        result=synthesize_templates(registry.records(subject),**selection)
        if result['source_corpus_sha256']!=source_corpus_sha256: raise ValueError('STALE_CORPUS_TEMPLATE')
        template=next((r for r in result['templates'] if r['template_sha256']==template_sha256),None)
        if template is None: raise ValueError('TEMPLATE_NOT_FOUND')
        return {'ok':True,'document_id':target_document_id,**compile_template(template,targets_by_role,expected_revision=int(meta['revision']))}

    return registry
