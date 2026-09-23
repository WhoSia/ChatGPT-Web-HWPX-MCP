"""Evidence-guided alternatives; frequency never confers aesthetic authority."""
from collections import Counter, defaultdict
import math

from p335_corpus import _sha, _stable
from p335_registry import registry_snapshot
from p335_paragraph import build_style_transfer_operations


def _distribution(rows, weight):
    counter=Counter()
    for row in rows: counter[row['preset_sha256']]+=weight(row)
    total=sum(counter.values())
    shares=[n/total for n in counter.values()] if total else []
    return {'total':total,'shares':{k:round(v/total,8) for k,v in sorted(counter.items())} if total else {},
            'entropy_bits':round(-sum(p*math.log2(p) for p in shares),8),
            'concentration':round(sum(p*p for p in shares),8)}


def build_style_atlas(records, *, institution=None, role=None, source_family=None, dimension=None):
    snap=registry_snapshot(records)
    # Exact byte copies cannot vote more than once, even if attributed twice.
    # Keep aliases and all source receipts available for audit.
    selected=[r for r in snap['records'] if r['inclusion_status']=='INCLUDED'
              and (institution is None or r['institution']==institution)
              and (source_family is None or r['source_family']==source_family)]
    unique={}
    for r in selected: unique.setdefault(r['sha256'],r)
    rows=[]
    for r in unique.values():
        for exemplar in r['observations']['roles']:
            if role is not None and exemplar['role']!=role: continue
            preset=exemplar['authoring_preset']
            if dimension:
                if dimension not in {'run_format','paragraph_format'}: raise ValueError('INVALID_STYLE_DIMENSION')
                preset={dimension:preset.get(dimension,{})}
            rows.append({'source_id':r['source_id'],'institution':r['institution'],'role':exemplar['role'],
                         'source_receipt_sha256':r['source_receipt_sha256'],
                         'preset_sha256':_sha(preset),'authoring_preset':preset,
                         'volume':exemplar['weighted_characters_or_empty_paragraphs'],
                         'native_readback':exemplar['native_readback']})
    roles=[]
    for name in sorted({r['role'] for r in rows}):
        group=[r for r in rows if r['role']==name]
        docdist=_distribution(group,lambda _:1); voldist=_distribution(group,lambda r:r['volume'])
        institutions=Counter(r['institution'] for r in group)
        instdist=_distribution(group,lambda r:1/institutions[r['institution']])
        candidates=[]
        for fingerprint in sorted({r['preset_sha256'] for r in group}):
            matches=[r for r in group if r['preset_sha256']==fingerprint]
            candidates.append({'candidate_id':name+':'+fingerprint,'preset_sha256':fingerprint,
                               'authoring_preset':matches[0]['authoring_preset'],
                               'documents':len(matches),'document_share':docdist['shares'][fingerprint],
                               'volume_share':voldist['shares'][fingerprint],
                               'institution_balanced_share':instdist['shares'][fingerprint],
                               'institutions':sorted({r['institution'] for r in matches}),
                               'source_ids':[r['source_id'] for r in matches],
                               'source_receipts':{r['source_id']:r['source_receipt_sha256'] for r in matches},
                               'native_readback':matches[0]['native_readback']})
        strata=[]
        for inst in sorted(institutions):
            matches=[r for r in group if r['institution']==inst]
            strata.append({'institution':inst,'document_distribution':_distribution(matches,lambda _:1),
                           'source_ids':[r['source_id'] for r in matches]})
        roles.append({'role':name,'document_distribution':docdist,'volume_distribution':voldist,
                      'institution_balanced_distribution':instdist,'institutions':strata,'candidates':candidates})
    result={'schema':'hwpx-style-atlas/v1','corpus_sha256':snap['corpus_sha256'],'registry_sha256':snap['registry_sha256'],
            'filters':{'institution':institution,'role':role,'source_family':source_family,'dimension':dimension},
            'unique_documents':len(unique),'exact_duplicates':snap['exact_duplicates'],'roles':roles,
            'source_index':{r['source_id']:{'receipt_sha256':r['source_receipt_sha256'],'institution':r['institution'],
                          'typography_profile_sha256':r['observations']['typography']['profile_sha256'],
                          'paragraph_profile_sha256':r['observations']['paragraph']['profile_sha256']} for r in selected},
            'authority':'OBSERVED_STYLE_DISTRIBUTIONS_ONLY',
            'variation_policy':'Within-document distributions remain in source observations; role/institution distributions retain every regime. No automatic winner.',
            'visual_comparison_status':'HOLD_UNLESS_PAIRED_CONTROLS_OBSERVED'}
    result['atlas_sha256']=_sha(result)
    return result


def synthesize_templates(records, *, mode='CORPUS_SUPPORTED', source_id=None, roles=None,
                         institution=None, min_documents=2, min_share=0.5):
    if mode not in {'EXPLICIT_EXEMPLAR','CORPUS_SUPPORTED','COHERENT_BUNDLE'}: raise ValueError('INVALID_SYNTHESIS_MODE')
    if not isinstance(min_documents,int) or isinstance(min_documents,bool) or min_documents<1 or not 0<float(min_share)<=1:
        raise ValueError('INVALID_SUPPORT_THRESHOLD')
    snap=registry_snapshot(records)
    selected=[r for r in records if r['inclusion_status']=='INCLUDED' and (not institution or r['institution']==institution)]
    if roles is not None and (not roles or len(roles)>12 or len(set(roles))!=len(roles)):
        raise ValueError('INVALID_ROLE_SELECTION')
    templates=[]

    def emit(presets, sources, support, compatibility):
        unresolved=[];safe={}
        for role_name,preset in presets.items():
            safe[role_name]={}
            for group,values in preset.items():
                safe[role_name][group]={k:v for k,v in values.items() if not k.endswith('_readback_only')}
                unresolved.extend({'role':role_name,'dimension':k,'status':'READBACK_ONLY'} for k in values if k.endswith('_readback_only'))
        unresolved.append({'dimension':'native_tab_property_and_script_ratio_relative_size_offset','status':'READBACK_ONLY'})
        row={'schema':'hwpx-template-candidate/v1','source_corpus_sha256':snap['corpus_sha256'],
             'synthesis_mode':mode,'role_presets':safe,'support':support,
             'source_ids':sorted(r['source_id'] for r in sources),
             'source_receipts':{r['source_id']:r['source_receipt_sha256'] for r in sources},
             'institutions':sorted({r['institution'] for r in sources}),
             'dimension_provenance':{name:{group:{key:sorted(r['source_id'] for r in sources) for key in values} for group,values in preset.items()} for name,preset in safe.items()},
             'unresolved_dimensions':unresolved,'compatibility_notes':compatibility,
             'authority':'EVIDENCE_GUIDED_TEMPLATE_CANDIDATE'}
        row['template_sha256']=_sha(row);row['template_id']='tpl_'+row['template_sha256'][:24]
        templates.append(row)

    if mode=='EXPLICIT_EXEMPLAR':
        source=next((r for r in selected if r['source_id']==source_id),None)
        if source is None: raise ValueError('INCLUDED_SOURCE_NOT_FOUND')
        presets={r['role']:r['authoring_preset'] for r in source['observations']['roles'] if roles is None or r['role'] in roles}
        if roles and set(roles)-set(presets): raise ValueError('SOURCE_MISSING_REQUESTED_ROLES')
        emit(presets,[source],{'documents':1},'Observed together in one source; no native rendering claim.')
    elif mode=='CORPUS_SUPPORTED':
        atlas=build_style_atlas(selected)
        for role_row in atlas['roles']:
            if roles and role_row['role'] not in roles: continue
            for candidate in role_row['candidates']:
                if candidate['documents']>=min_documents and candidate['document_share']>=min_share:
                    sources=[r for r in selected if r['source_id'] in candidate['source_ids']]
                    emit({role_row['role']:candidate['authoring_preset']},sources,
                         {k:candidate[k] for k in ('documents','document_share','volume_share','institution_balanced_share')},
                         'One role candidate. Alternatives remain separate; multi-role composition requires co-occurrence.')
    else:
        if not roles: raise ValueError('BUNDLE_REQUIRES_EXPLICIT_ROLES')
        groups=defaultdict(list); seen=set()
        for source in sorted(selected,key=lambda r:r['source_id']):
            if source['sha256'] in seen: continue
            seen.add(source['sha256'])
            presets={r['role']:r['authoring_preset'] for r in source['observations']['roles'] if r['role'] in roles}
            if set(presets)!=set(roles): continue
            # Co-occurrence and institutional compatibility, not independently
            # popular dimensions, establish a bundle's support.
            groups[(source['institution'],_stable(presets))].append(source)
        for (inst,payload),sources in sorted(groups.items()):
            denominator=len({r['sha256'] for r in selected if r['institution']==inst})
            share=len(sources)/max(1,denominator)
            if len(sources)>=min_documents and share>=min_share:
                import json
                emit(json.loads(payload),sources,{'documents':len(sources),'institution_document_share':share},
                     'All roles co-occur with identical presets within one institution; no cross-institution mixing.')
    return {'schema':'hwpx-template-synthesis/v1','source_corpus_sha256':snap['corpus_sha256'],
            'status':'CANDIDATES' if templates else 'INSUFFICIENT_COMPATIBLE_SUPPORT','templates':templates,
            'selection_policy':'EXPLICIT_SELECTION_REQUIRED_NO_AUTOMATIC_AESTHETIC_WINNER'}


def compile_template(template, targets_by_role, *, expected_revision):
    clean={k:v for k,v in template.items() if k not in {'template_id','template_sha256'}}
    if _sha(clean)!=template.get('template_sha256'): raise ValueError('TEMPLATE_HASH_MISMATCH')
    if not isinstance(expected_revision,int) or expected_revision<1: raise ValueError('INVALID_TARGET_REVISION')
    if not targets_by_role or set(targets_by_role)-set(template['role_presets']): raise ValueError('UNKNOWN_TEMPLATE_ROLE')
    all_targets=[t for targets in targets_by_role.values() for t in targets]
    if len(all_targets)>100 or len(all_targets)!=len(set(all_targets)): raise ValueError('TARGET_LIMIT_OR_ROLE_COLLISION')
    operations=[]
    for name,targets in sorted(targets_by_role.items()):
        operations.extend(build_style_transfer_operations({'authoring_preset':template['role_presets'][name]},targets))
    return {'operations':operations,'expected_revision':expected_revision,'apply_with':'apply_formatting',
            'atomicity':'EXISTING_VALIDATION_CAS_ROLLBACK','template_sha256':template['template_sha256'],
            'source_corpus_sha256':template['source_corpus_sha256']}
