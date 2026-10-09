from __future__ import annotations
import json,os
from pathlib import Path
from typing import Any,Mapping
import psycopg
from hwpx_mcp.quality.p44_health_intelligence import canonical_corpus_provenance,canonical_release_observation
ROOT=Path(__file__).resolve().parents[2]
class DurableHealthIntelligenceStore:
    def __init__(self,database_url:str)->None:
        if not database_url:raise RuntimeError("P44 health intelligence requires Postgres")
        self.database_url=database_url;self._ensure_schema()
    @property
    def mode(self)->str:return "postgres-append-only-quality-intelligence"
    def _connect(self,*,autocommit:bool=True):return psycopg.connect(self.database_url,autocommit=autocommit)
    def _ensure_schema(self)->None:
        with self._connect() as c,c.cursor() as q:
            q.execute("""CREATE TABLE IF NOT EXISTS hwpx_release_health_event(event_id TEXT PRIMARY KEY,phase TEXT NOT NULL,product TEXT NOT NULL,exact_head TEXT NOT NULL,observed_at TIMESTAMPTZ NOT NULL,feature_family TEXT,payload_sha256 TEXT NOT NULL,payload JSONB NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
            q.execute("CREATE INDEX IF NOT EXISTS hwpx_release_health_event_time_idx ON hwpx_release_health_event(observed_at,created_at)")
            q.execute("""CREATE TABLE IF NOT EXISTS hwpx_corpus_provenance_event(event_id TEXT PRIMARY KEY,source_id TEXT NOT NULL,federation_namespace TEXT NOT NULL,feature_family TEXT,source_kind TEXT NOT NULL,payload_sha256 TEXT NOT NULL,payload JSONB NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
            q.execute("CREATE INDEX IF NOT EXISTS hwpx_corpus_provenance_namespace_idx ON hwpx_corpus_provenance_event(federation_namespace,feature_family)")
    def append_release_observation(self,o:Mapping[str,Any])->dict:
        p=canonical_release_observation(o);d=p["observation_sha256"];eid="release:"+d
        with self._connect() as c,c.cursor() as q:
            q.execute("INSERT INTO hwpx_release_health_event(event_id,phase,product,exact_head,observed_at,feature_family,payload_sha256,payload) VALUES(%s,%s,%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT(event_id) DO NOTHING",
                      (eid,p["phase"],p["product"],p["exact_head"],p["observed_at"],p.get("feature_family") or None,d,json.dumps(p,ensure_ascii=False)));ins=q.rowcount==1
        return {"event_id":eid,"inserted":ins,"payload_sha256":d}
    def append_corpus_provenance(self,r:Mapping[str,Any])->dict:
        p=canonical_corpus_provenance(r);d=p["provenance_sha256"];eid="corpus:"+d
        with self._connect() as c,c.cursor() as q:
            q.execute("INSERT INTO hwpx_corpus_provenance_event(event_id,source_id,federation_namespace,feature_family,source_kind,payload_sha256,payload) VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT(event_id) DO NOTHING",
                      (eid,p["source_id"],p["federation_namespace"],p.get("feature_family") or None,p["source_kind"],d,json.dumps(p,ensure_ascii=False)));ins=q.rowcount==1
        return {"event_id":eid,"inserted":ins,"payload_sha256":d}
    def query_release_observations(self,*,limit:int=200,phase:str="",feature_family:str="")->list[dict]:
        clauses=[];params=[]
        if phase:clauses.append("phase=%s");params.append(phase)
        if feature_family:clauses.append("feature_family=%s");params.append(feature_family)
        where=" WHERE "+" AND ".join(clauses) if clauses else "";params.append(max(1,min(int(limit),1000)))
        with self._connect() as c,c.cursor() as q:q.execute(f"SELECT payload::text FROM hwpx_release_health_event{where} ORDER BY observed_at ASC,created_at ASC LIMIT %s",tuple(params));rows=q.fetchall()
        return [json.loads(x[0]) for x in rows]
    def query_corpus_provenance(self,*,limit:int=500,feature_family:str="",namespace:str="")->list[dict]:
        clauses=[];params=[]
        if feature_family:clauses.append("feature_family=%s");params.append(feature_family)
        if namespace:clauses.append("federation_namespace=%s");params.append(namespace)
        where=" WHERE "+" AND ".join(clauses) if clauses else "";params.append(max(1,min(int(limit),2000)))
        with self._connect() as c,c.cursor() as q:q.execute(f"SELECT payload::text FROM hwpx_corpus_provenance_event{where} ORDER BY created_at ASC LIMIT %s",tuple(params));rows=q.fetchall()
        return [json.loads(x[0]) for x in rows]
    def bootstrap(self,*,release_seed:Path|str=ROOT/"benchmarks"/"p44_release_seed.json",external_manifest:Path|str=ROOT/"corpus"/"p43-immutable-external-fixtures.json",federation_registry:Path|str=ROOT/"corpus"/"p44-federation-registry.json")->dict:
        ir=ic=0;seed=json.loads(Path(release_seed).read_text(encoding="utf-8"))
        for x in seed.get("entries",[]):ir+=int(self.append_release_observation(x)["inserted"])
        reg=json.loads(Path(federation_registry).read_text(encoding="utf-8"));sm={str(x["namespace"]):x for x in reg.get("sources",[])}
        for x in reg.get("source_records",[]):ic+=int(self.append_corpus_provenance(x)["inserted"])
        for x in json.loads(Path(external_manifest).read_text(encoding="utf-8")):
            repo=str(x.get("repository") or "");m=sm.get(repo,{})
            rec={"record_kind":"DOCUMENT","source_id":x["source_id"],"federation_namespace":repo or "immutable-upstream","institution":m.get("institution") or repo,
                 "archetype":m.get("archetype") or x.get("feature_family",""),"feature_family":x.get("feature_family",""),"source_kind":"IMMUTABLE_UPSTREAM","repository":repo,
                 "upstream_commit":x.get("commit",""),"git_blob_sha":x.get("git_blob_sha",""),"license":x.get("license",""),"blocking":True,
                 "acquisition_status":"EXACT_COMMIT_AND_BLOB_PINNED","observed_at":"2026-09-29T05:08:04+00:00"}
            ic+=int(self.append_corpus_provenance(rec)["inserted"])
        return {"mode":self.mode,"release_inserted":ir,"corpus_inserted":ic,"release_count":len(self.query_release_observations(limit=1000)),"corpus_count":len(self.query_corpus_provenance(limit=2000))}
def default_database_url()->str:return os.environ.get("P44_HEALTH_DATABASE_URL","").strip() or os.environ.get("P30_DOCUMENT_DATABASE_URL","").strip() or os.environ.get("P12_AUTH_DATABASE_URL","").strip()
