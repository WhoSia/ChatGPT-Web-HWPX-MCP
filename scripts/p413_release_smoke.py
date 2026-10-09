from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from hwpx_mcp.evidence.p413_evidence_service import evidence_health_summary, public_authoring_trust_status, release_manifest

m=release_manifest()
h=evidence_health_summary()
t=public_authoring_trust_status()
assert m["product"]=="0.38.0-p4.13"
assert m["baseline_case_count"]==5
assert h["status"]=="PASS"
assert t["status"]=="TRUST_BASELINE_ACTIVE"
print("P4.13 evidence/trust service smoke PASS")
