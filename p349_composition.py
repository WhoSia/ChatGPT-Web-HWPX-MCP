from __future__ import annotations
import copy,hashlib,json,os,shutil,subprocess,threading
from pathlib import Path
from typing import Any,Mapping,Sequence
from p347_supply_chain_bridge import compare_host_conformance
from p347_trust import verify_host_observations
ROOT=Path(__file__).resolve().parent
def _stable(v:Any)->str:return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"))
def _sha(v:Any)->str:return hashlib.sha256(_stable(v).encode()).hexdigest()
def _node()->str:
    explicit=str(os.environ.get("P349_NODE_BIN") or "").strip();found=explicit or shutil.which("node") or shutil.which("nodejs")
    if not found:raise RuntimeError("P3.49 requires Node.js")
    return found
def _runtime()->Path:
    explicit=str(os.environ.get("P349_TS_RUNTIME") or "").strip()
    for p in [Path(explicit) if explicit else None,ROOT/"runtime"/"scripts"/"p349_composition_cli.js",ROOT/".tmp"/"p349-ts"/"scripts"/"p349_composition_cli.js"]:
        if p is not None and p.is_file():return p.resolve()
    raise RuntimeError("P3.49 compiled composition kernel is unavailable")
def _call(command:str,payload:Mapping[str,Any]|None=None)->dict:
    proc=subprocess.run([_node(),"--max-old-space-size=64",str(_runtime()),command],input="" if payload is None else _stable(payload),text=True,capture_output=True,timeout=6,check=False,env={"PATH":os.environ.get("PATH",""),"NODE_NO_WARNINGS":"1","LANG":os.environ.get("LANG","C.UTF-8")})
    if proc.returncode:raise RuntimeError("P3.49 TypeScript composition kernel failed: "+(proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}"))
    out=json.loads(proc.stdout)
    if not isinstance(out,dict):raise RuntimeError("P3.49 kernel result must be object")
    return out
def composition_contract()->dict:return _call("contract")
def analyze_composition(request:Mapping[str,Any])->dict:return _call("analyze",request)
def _record_from_registry(registry,document_id:str,package_id:str)->dict:
    item=registry.package_record(document_id,package_id);normalized=item["normalized"];ext=normalized["extension"];cert=item["certificate"]
    return {"package_id":package_id,"extension_id":ext["extension_id"],"version":ext["version"],"certificate_sha256":cert["certificate_sha256"],"dependencies":copy.deepcopy(normalized.get("dependencies") or []),"capabilities":copy.deepcopy(ext.get("capabilities") or []),"tools":copy.deepcopy(ext.get("tools") or [])}
class CompositionRegistry:
    def __init__(self,p347_registry,adapter_registry):
        self.p347=p347_registry;self.adapters=adapter_registry;self._lock=threading.RLock();self._generation={};self._certified={};self._active={};self._history={}
    def _state(self,document_id:str):
        if not document_id:raise ValueError("P3.49 composition requires document_id")
        if document_id not in self._generation:self._generation[document_id]=1;self._certified[document_id]={};self._active[document_id]=None;self._history[document_id]=[]
        return self._generation[document_id],self._certified[document_id],self._active[document_id],self._history[document_id]
    def snapshot(self,document_id:str)->dict:
        with self._lock:
            generation,certified,active,history=self._state(document_id)
            return {"phase":"P3.49","document_id":document_id,"generation":generation,"active_composition_id":active,"certified_compositions":[{"composition_id":k,"package_ids":v["serial_order"],"status":v["status"]} for k,v in sorted(certified.items())],"history":copy.deepcopy(history[-24:]),"authority":"OWNER_SCOPED_CERTIFIED_COMPOSITION_POINTER"}
    def analyze(self,document_id:str,package_ids:Sequence[str],serial_order:Sequence[str],max_effect:str="DELIVERY")->dict:
        snap=self.p347.snapshot(document_id);promoted=set((snap.get("promoted_by_extension") or {}).values());requested=[str(x) for x in package_ids];missing=[x for x in requested if x not in promoted]
        if missing:return {"status":"FAIL","conflicts":[{"type":"PACKAGE_NOT_PROMOTED","packages":missing}],"minimal_culpable_packages":sorted(missing),"authority":"P349_PRECONDITION_FAIL"}
        records=[_record_from_registry(self.p347,document_id,p) for p in requested];adapter=self.adapters.snapshot(document_id);policy=self.p347.trust_policy(document_id)
        req={"schema":"chatgpt-web-hwpx-mcp/p3.49/composition-request/v1","packages":records,"serial_order":list(serial_order),"max_effect":max_effect,"environment":{"p347_registry_generation":snap["generation"],"trust_policy_sha256":policy["trust_policy_sha256"],"p346_adapter_generation":adapter["generation"],"p346_adapter_contract_sha256":adapter["active_contract_sha256"],"joint_host_conformance_sha256":"0"*64}}
        out=analyze_composition(req);out["authority"]="DESCRIPTIVE_ONLY_NOT_ACTIVATION_AUTHORITY";return out
    def certify(self,document_id:str,package_ids:Sequence[str],serial_order:Sequence[str],joint_host_observations:Sequence[Mapping[str,Any]],expected_registry_generation:int,max_effect:str="DELIVERY")->dict:
        snap=self.p347.snapshot(document_id)
        if int(expected_registry_generation)!=int(snap["generation"]):raise RuntimeError("P3.49 P3.47 registry generation CAS mismatch")
        promoted=set((snap.get("promoted_by_extension") or {}).values());requested=[str(x) for x in package_ids];missing=[x for x in requested if x not in promoted]
        if missing:raise RuntimeError(f"P3.49 packages are not currently promoted: {missing}")
        policy=self.p347.trust_policy(document_id);host_trust=verify_host_observations(joint_host_observations,policy);conformance=compare_host_conformance(joint_host_observations)
        if not host_trust.get("trusted") or conformance.get("verdict")!="PASS":raise RuntimeError("P3.49 joint host recertification failed")
        adapter=self.adapters.snapshot(document_id);records=[_record_from_registry(self.p347,document_id,p) for p in requested]
        req={"schema":"chatgpt-web-hwpx-mcp/p3.49/composition-request/v1","packages":records,"serial_order":list(serial_order),"max_effect":max_effect,"environment":{"p347_registry_generation":snap["generation"],"trust_policy_sha256":policy["trust_policy_sha256"],"p346_adapter_generation":adapter["generation"],"p346_adapter_contract_sha256":adapter["active_contract_sha256"],"joint_host_conformance_sha256":conformance["conformance_sha256"]}}
        result=analyze_composition(req)
        if result["status"]!="PASS":return {**result,"joint_host_trust":host_trust,"joint_host_conformance":conformance}
        with self._lock:
            generation,certified,active,history=self._state(document_id);cid=result["composition_id"];sealed={**copy.deepcopy(result),"joint_host_trust_sha256":_sha(host_trust),"joint_host_conformance":copy.deepcopy(conformance)};prior=certified.get(cid)
            if prior is not None and _stable(prior)!=_stable(sealed):raise RuntimeError("P3.49 composition ID collision")
            certified[cid]=sealed;history.append({"action":"CERTIFY","composition_id":cid,"generation":generation});return {**copy.deepcopy(sealed),"composition_generation":generation,"authority":"P349_JOINT_HOST_RECERTIFIED_COMPOSITION_PASS"}
    def _assert_environment(self,document_id:str,manifest:Mapping[str,Any],expected_registry_generation:int|None=None):
        snap=self.p347.snapshot(document_id);env=manifest["environment"]
        if expected_registry_generation is not None and int(expected_registry_generation)!=int(snap["generation"]):raise RuntimeError("P3.49 expected P3.47 registry generation mismatch")
        if int(env["p347_registry_generation"])!=int(snap["generation"]):raise RuntimeError("P3.49 certified composition stale after P3.47 registry change")
        if str(env["trust_policy_sha256"])!=str(snap.get("trust_policy_sha256")):raise RuntimeError("P3.49 trust policy drift")
        adapter=self.adapters.snapshot(document_id)
        if int(env["p346_adapter_generation"])!=int(adapter["generation"]) or str(env["p346_adapter_contract_sha256"])!=str(adapter["active_contract_sha256"]):raise RuntimeError("P3.49 host adapter profile drift")
        promoted=set((snap.get("promoted_by_extension") or {}).values());package_ids={x["package_id"] for x in manifest["packages"]}
        if not package_ids.issubset(promoted):raise RuntimeError("P3.49 certified composition contains no-longer-promoted package")
    def activate(self,document_id:str,composition_id:str,expected_generation:int,expected_registry_generation:int)->dict:
        with self._lock:
            generation,certified,active,history=self._state(document_id)
            if int(expected_generation)!=generation:raise RuntimeError("P3.49 composition generation CAS mismatch")
            if composition_id not in certified:raise KeyError("P3.49 composition is not certified")
            manifest=certified[composition_id];self._assert_environment(document_id,manifest,expected_registry_generation);previous=active
            if previous==composition_id:raise RuntimeError("P3.49 composition is already active")
            self._active[document_id]=composition_id;self._generation[document_id]=generation+1;history.append({"action":"ACTIVATE","from":previous,"to":composition_id,"generation_before":generation,"generation_after":generation+1})
            return {**self.snapshot(document_id),"previous_composition_id":previous,"activated_composition_id":composition_id,"authority":"ATOMIC_CERTIFIED_COMPOSITION_ACTIVATION_PASS"}
    def rollback(self,document_id:str,expected_generation:int)->dict:
        with self._lock:
            generation,certified,active,history=self._state(document_id)
            if int(expected_generation)!=generation:raise RuntimeError("P3.49 composition generation CAS mismatch")
            if not active:raise RuntimeError("P3.49 no active composition")
            previous=None
            for row in reversed(history):
                if row.get("action")=="ACTIVATE" and row.get("to")==active and row.get("from"):previous=row["from"];break
            if not previous or previous not in certified:raise RuntimeError("P3.49 no prior certified composition rollback target")
            self._assert_environment(document_id,certified[previous]);self._active[document_id]=previous;self._generation[document_id]=generation+1;history.append({"action":"ROLLBACK","from":active,"to":previous,"generation_before":generation,"generation_after":generation+1})
            return {**self.snapshot(document_id),"retired_composition_id":active,"restored_composition_id":previous,"authority":"ATOMIC_CERTIFIED_COMPOSITION_ROLLBACK_PASS"}
