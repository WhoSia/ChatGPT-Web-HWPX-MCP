from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from p349_composition import analyze_composition,composition_contract
def rec(n,ext,effect="READ_ONLY",deps=None):return {"package_id":"sha256:"+n*64,"extension_id":ext,"version":"1.0.0","certificate_sha256":n*64,"dependencies":deps or [],"capabilities":[{"name":ext+".cap","version":"1.0.0","effect":effect,"adapter":ext.upper(),"deterministic":True}],"tools":[]}
a=rec("1","release.inspect");b=rec("2","release.edit","DOCUMENT_MUTATION",[{"package_id":a["package_id"],"extension_id":a["extension_id"],"version":"1.0.0"}]);req={"schema":"chatgpt-web-hwpx-mcp/p3.49/composition-request/v1","packages":[a,b],"serial_order":[a["package_id"],b["package_id"]],"max_effect":"DOCUMENT_MUTATION","environment":{"p347_registry_generation":7,"trust_policy_sha256":"a"*64,"p346_adapter_generation":3,"p346_adapter_contract_sha256":"b"*64,"joint_host_conformance_sha256":"c"*64}};contract=composition_contract();assert contract["phase"]=="P3.49" and contract["product"]=="0.26.0-p3.49";out=analyze_composition(req);assert out["status"]=="PASS" and out["composition_id"].startswith("sha256:");bad=dict(req);bad["serial_order"]=[b["package_id"],a["package_id"]];assert analyze_composition(bad)["status"]=="FAIL";print("P3.49 release smoke PASS")
