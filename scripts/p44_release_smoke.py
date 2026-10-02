from __future__ import annotations
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from p44_health_intelligence import attribute_feature_families_from_evidence,build_operator_dashboard,build_support_bundle,health_intelligence_contract,route_native_render_escalation
contract=health_intelligence_contract();assert contract["product"]=="0.30.0-p4.4"
seed=json.loads((ROOT/"benchmarks"/"p44_release_seed.json").read_text(encoding="utf-8"));assert len(seed["entries"])==3;assert seed["entries"][-1]["exact_head"]=="a970def5bb92db5592b9e0e235baa98a8cd9ba1e"
registry=json.loads((ROOT/"corpus"/"p44-federation-registry.json").read_text(encoding="utf-8"));assert len(registry["sources"])>=4
a=attribute_feature_families_from_evidence({"document_sha256":"a"*64,"signals":{"hyperlink":True}});assert a["top_family"]=="HYPERLINKS"
route=route_native_render_escalation({"locus":"INDEPENDENT_ORACLE_DIVERGENCE","severity":"HIGH"});assert route["route"]=="NATIVE_RENDER_REQUIRED"
dashboard=build_operator_dashboard(seed["entries"],registry["source_records"]);bundle=build_support_bundle({"message":"P4.4 release smoke","token":"must-not-leak"},seed["entries"],registry["source_records"])
assert dashboard["release_observation_count"]==3 and "token" not in bundle["context"]
print(json.dumps({"phase":"P4.4","product":contract["product"],"release_seed_count":len(seed["entries"]),"federation_sources":len(registry["sources"]),"bundle_id":bundle["bundle_id"]}))
