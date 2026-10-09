from __future__ import annotations
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from hwpx_mcp.quality.p45_quality_control import active_corpus_governance,build_operator_alerts,quality_control_contract,slo_readiness
c=quality_control_contract();assert c["product"]=="0.31.0-p4.5"
rows=json.loads((ROOT/"benchmarks"/"p44_release_seed.json").read_text(encoding="utf-8"))["entries"]
assert slo_readiness(rows)["state"]=="PROVISIONAL_HARD_BUDGET"
assert active_corpus_governance(json.loads((ROOT/"corpus"/"p44-federation-registry.json").read_text(encoding="utf-8"))["source_records"])["freshness_is_release_blocking"] is False
assert build_operator_alerts(rows,[])["notification_authority"]=="NO_EXTERNAL_NOTIFICATION_SIDE_EFFECT"
print(json.dumps({"phase":"P4.5","product":c["product"],"baseline_observations":len(rows)}))
