"""Append-only source receipts and cached native observations (no document writer)."""
from __future__ import annotations

import hashlib
import json
import re
import zipfile
from xml.etree.ElementTree import ParseError
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from p335_corpus import _sha, _stable
from p335_paragraph import build_role_aware_style_exemplars, build_paragraph_geometry_profile
from p335_typography import build_typography_profile
from p334r2_package_validation import validate_hwpx_package_light
from p318_document_setup import build_document_setup_map

SCHEMA = 'hwpx-corpus-source/v1'
MAX_SOURCES = 500
ACCESS = {'PUBLICLY_ACCESSIBLE', 'LOCALLY_GENERATED_NATIVE_EVIDENCE', 'USER_PROVIDED_RESEARCH_EVIDENCE', 'UNVERIFIED'}
FIELDS = {'source_id','original_filename','title','source_url','institution','source_family','retrieved_at','access_status','license_statement','license_url','license_kind','provenance_notes','native_status'}


def validate_source_metadata(metadata: dict) -> dict:
    if not isinstance(metadata, dict) or set(metadata)-FIELDS:
        raise ValueError('INVALID_SOURCE_METADATA_FIELDS')
    row = dict(metadata)
    required = ('source_id','original_filename','institution','retrieved_at','access_status')
    if any(not isinstance(row.get(k),str) or not row[k].strip() for k in required):
        raise ValueError('MISSING_SOURCE_METADATA')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}',row['source_id']):
        raise ValueError('INVALID_SOURCE_ID')
    if '/' in row['original_filename'] or '\\' in row['original_filename']:
        raise ValueError('FILENAME_MUST_NOT_BE_PATH')
    if any(v is not None and (not isinstance(v,str) or len(v)>4000) for v in row.values()):
        raise ValueError('SOURCE_METADATA_LIMIT')
    try:
        stamp=datetime.fromisoformat(row['retrieved_at'].replace('Z','+00:00'))
        if stamp.tzinfo is None: raise ValueError()
    except ValueError: raise ValueError('RETRIEVAL_TIME_REQUIRES_TIMEZONE') from None
    if row['access_status'] not in ACCESS: raise ValueError('INVALID_ACCESS_STATUS')
    for key in ('source_url','license_url'):
        if row.get(key):
            url=urlsplit(row[key])
            if url.scheme not in ('https','http') or not url.hostname or url.username or url.password:
                raise ValueError('INVALID_PROVENANCE_URL')
    if row['access_status']=='PUBLICLY_ACCESSIBLE' and not row.get('source_url'):
        raise ValueError('PUBLIC_SOURCE_REQUIRES_URL')
    kind=row.get('license_kind') or 'UNKNOWN'
    if kind not in {'UNKNOWN','EXPLICIT_OPEN_LICENSE','RESTRICTED'}: raise ValueError('INVALID_LICENSE_KIND')
    if kind!='UNKNOWN' and not (row.get('license_statement') and row.get('license_url')):
        raise ValueError('LICENSE_CLAIM_REQUIRES_STATEMENT_AND_SOURCE')
    row.update(license_kind=kind, reuse_status=kind if kind!='UNKNOWN' else 'UNKNOWN_REUSE_RIGHTS')
    row.setdefault('source_family','unspecified'); row.setdefault('title',row['original_filename'])
    # User declarations never promote native application fidelity.
    row['native_status'] = row.get('native_status') or 'NOT_OBSERVED'
    row['native_status_provenance'] = 'DECLARED_NOT_INDEPENDENTLY_VERIFIED'
    row['redistribution_authorized'] = False
    return row


def _bounded_package(path: Path):
    if path.stat().st_size>8_000_000: raise ValueError('SOURCE_BYTES_LIMIT')
    with zipfile.ZipFile(path) as z:
        infos=z.infolist()
        if len(infos)>512 or sum(i.file_size for i in infos)>32_000_000:
            raise ValueError('EXPANDED_PACKAGE_LIMIT')
        if any(i.file_size>8_000_000 or i.file_size/max(1,i.compress_size)>100 for i in infos):
            raise ValueError('ENTRY_EXPANSION_LIMIT')
    return validate_hwpx_package_light(path)


def intake_source(metadata: dict, path: Path | None = None, *, document_id=None, revision=None) -> dict:
    row=validate_source_metadata(metadata)
    row.update(schema=SCHEMA, sha256=None, byte_size=None, package_status='NOT_ACQUIRED', parser_status='NOT_RUN',
               role_status='NOT_RUN', inclusion_status='EXCLUDED', exclusion_reason='BYTES_NOT_ACQUIRED',
               controls=[], annotations=[], observations=None, document_id=document_id, document_revision=revision)
    if path is not None:
        raw=path.read_bytes() if path.stat().st_size<=8_000_000 else None
        if raw is None: raise ValueError('SOURCE_BYTES_LIMIT')
        row.update(sha256=hashlib.sha256(raw).hexdigest(),byte_size=len(raw))
        try:
            _bounded_package(path)
        except (ValueError, zipfile.BadZipFile, KeyError, ParseError, RuntimeError):
            row.update(package_status='REJECTED',exclusion_reason='INVALID_HWPX_PACKAGE')
        else:
            row['package_status']='VALID'
            try:
                roles=build_role_aware_style_exemplars(path)
                typography=build_typography_profile(path)
                paragraph=build_paragraph_geometry_profile(path)
                setup=build_document_setup_map(path)
                # Cached once at intake. Querying receipts/atlas never reopens HWPX.
                observations={'roles':roles['roles'],'role_profile_sha256':roles['profile_sha256'],
                              'classification_policy':roles['classification_policy'],
                              'role_evidence_counts':roles['evidence_counts'],
                              'empty_paragraphs':roles['excluded_empty_paragraph_count'],
                              'typography':typography,'paragraph':paragraph,
                              'document_setup':{'source_setup_sha256':setup['document_setup_sha256'],
                                  'sections':[{k:v for k,v in section.items() if k!='stories'} |
                                              {'stories':[{k:v for k,v in story.items() if k!='text'} for story in section['stories']]}
                                              for section in setup['sections']]}}
                row.update(parser_status='PASS',role_status='PASS' if roles['roles'] else 'NO_TEXTUAL_ROLES',
                           inclusion_status='INCLUDED' if roles['roles'] else 'EXCLUDED',
                           exclusion_reason=None if roles['roles'] else 'NO_TEXTUAL_ROLES',observations=observations)
                # This is style similarity, explicitly not semantic identity.
                row['style_fingerprint']=_sha([(r['role'],r['authoring_preset']) for r in roles['roles']])
            except Exception as exc:
                row.update(parser_status='FAILED',exclusion_reason='PARSER_READBACK_FAILED',parser_error_type=type(exc).__name__)
    row['source_receipt_sha256']=_sha(row)
    return row


def seal_source(row: dict) -> dict:
    clean={k:v for k,v in row.items() if k!='source_receipt_sha256'}
    return {**clean,'source_receipt_sha256':_sha(clean)}


def validate_receipt(row: dict):
    if row.get('schema')!=SCHEMA or seal_source(row)['source_receipt_sha256']!=row.get('source_receipt_sha256'):
        raise ValueError('SOURCE_RECEIPT_HASH_MISMATCH')


def registry_snapshot(records: list[dict]) -> dict:
    if len(records)>MAX_SOURCES: raise ValueError('CORPUS_SOURCE_LIMIT')
    ids=[r['source_id'] for r in records]
    if len(set(ids))!=len(ids): raise ValueError('DUPLICATE_SOURCE_ID')
    for row in records: validate_receipt(row)
    ordered=sorted(records,key=lambda r:r['source_id'])
    duplicate_groups={}
    style_groups={}
    for row in ordered:
        if row.get('sha256'): duplicate_groups.setdefault(row['sha256'],[]).append(row['source_id'])
        if row.get('style_fingerprint'): style_groups.setdefault(row['style_fingerprint'],[]).append(row['source_id'])
    active=[r for r in ordered if r['inclusion_status']=='INCLUDED']
    return {'schema':'hwpx-corpus-registry/v1','records':ordered,
            'registry_sha256':_sha([(r['source_id'],r['source_receipt_sha256']) for r in ordered]),
            'corpus_sha256':_sha([(r['source_id'],r['source_receipt_sha256']) for r in active]),
            'exact_duplicates':[v for v in duplicate_groups.values() if len(v)>1],
            'style_similarity_groups':[v for v in style_groups.values() if len(v)>1],
            'near_duplicate_authority':'STYLE_SIMILARITY_ONLY_NOT_SEMANTIC_IDENTITY',
            'coverage':{'sources':len(ordered),'included':len(active),'excluded':len(ordered)-len(active),
                        'institutions':dict(sorted(Counter(r['institution'] for r in active).items())),
                        'reuse_status':dict(sorted(Counter(r['reuse_status'] for r in ordered).items())),
                        'controls':sum(bool(r['controls']) for r in ordered)}}


class PostgresCorpusRegistry:
    """Owner-isolated, append-only encrypted receipts using existing custody crypto.

    A source update needs the last receipt hash (CAS). Extracted observations
    survive document expiry; source bytes are not duplicated or redistributed.
    """
    def __init__(self, document_store):
        self.store=document_store
        with self.store._connect() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS hwpx_corpus_receipts (
                owner_subject TEXT NOT NULL, source_id TEXT NOT NULL, revision INTEGER NOT NULL,
                receipt_sha256 TEXT NOT NULL, encrypted_payload BYTEA NOT NULL,
                PRIMARY KEY(owner_subject,source_id,revision))''')

    def _aad(self, owner, source):
        return ('hwpx-corpus/v1\0'+owner+'\0'+source).encode()

    def records(self, owner):
        with self.store._connect() as conn:
            rows=conn.execute('''SELECT DISTINCT ON(source_id) source_id,encrypted_payload
                FROM hwpx_corpus_receipts WHERE owner_subject=%s
                ORDER BY source_id,revision DESC LIMIT %s''',(owner,MAX_SOURCES+1)).fetchall()
        if len(rows)>MAX_SOURCES: raise ValueError('CORPUS_SOURCE_LIMIT')
        return [json.loads(self.store._open(bytes(payload),self._aad(owner,source))) for source,payload in rows]

    def get(self, owner, source_id, revision=None):
        with self.store._connect() as conn:
            row=conn.execute('''SELECT encrypted_payload FROM hwpx_corpus_receipts
                WHERE owner_subject=%s AND source_id=%s AND (%s::integer IS NULL OR revision=%s)
                ORDER BY revision DESC LIMIT 1''',(owner,source_id,revision,revision)).fetchone()
        if row is None: raise ValueError('SOURCE_NOT_FOUND')
        result=json.loads(self.store._open(bytes(row[0]),self._aad(owner,source_id)))
        validate_receipt(result)
        return result

    def append(self, owner, row, expected_receipt=None):
        validate_receipt(row); source=row['source_id']
        if len(_stable(row).encode())>2_000_000: raise ValueError('SOURCE_OBSERVATION_LIMIT')
        payload=self.store._seal(_stable(row).encode(),self._aad(owner,source))
        with self.store._connect(autocommit=False) as conn:
            # Serialize intake and capacity checks per owner, not globally.
            conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',('corpus:'+owner,))
            last=conn.execute('''SELECT revision,receipt_sha256 FROM hwpx_corpus_receipts
                WHERE owner_subject=%s AND source_id=%s ORDER BY revision DESC LIMIT 1''',(owner,source)).fetchone()
            if last and last[1]==row['source_receipt_sha256']: return {'revision':last[0],'idempotent':True}
            if (last[1] if last else None)!=expected_receipt: raise ValueError('SOURCE_RECEIPT_CAS_CONFLICT')
            if not last:
                count=conn.execute('SELECT COUNT(DISTINCT source_id) FROM hwpx_corpus_receipts WHERE owner_subject=%s',(owner,)).fetchone()[0]
                if count>=MAX_SOURCES: raise ValueError('CORPUS_SOURCE_LIMIT')
            revision=last[0]+1 if last else 1
            conn.execute('INSERT INTO hwpx_corpus_receipts VALUES(%s,%s,%s,%s,%s)',(owner,source,revision,row['source_receipt_sha256'],payload))
        return {'revision':revision,'idempotent':False}
