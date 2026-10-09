from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from hwpx_mcp.quality.p43_quality import adjudicate_release_health,load_release_history,quality_service_contract
c=quality_service_contract();assert c["product"]=="0.29.0-p4.3"
h=load_release_history();assert h["entry_count"]>=2
r=adjudicate_release_health({"feature_family_count":12,"external_document_count":8,"external_repository_count":2,"generated_fixture_count":24,"product_authority_pass":True,"independent_oracle_coverage":0.9,"performance_budget_pass":True,"diagnostic_negative_control_pass":True,"docker_pass":True,"rollback_ready":True,"critical_failure_count":0})
assert r["verdict"]=="PASS"
print("P4.3 release smoke PASS")
