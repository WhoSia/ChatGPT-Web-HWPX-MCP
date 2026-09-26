from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from p344_autonomous_authoring import autonomous_authoring_contract,evaluate_runtime_gate,new_run,verify_run

contract=autonomous_authoring_contract()
assert contract["phase"]=="P3.44"
snapshot={
 "static_verdict":"PASS","render_requirement":"REQUIRED","render_verdict":"NOT_PROVIDED",
 "repairable":False,"repairs_used":0,"max_repairs":2,"policy_ok":True,"footprint_ok":True,
 "human_requirement":"NOT_REQUIRED","human_verdict":"PENDING"
}
gate=evaluate_runtime_gate(snapshot,require_rust=bool(os.environ.get("P344_REQUIRE_RUST_GATE")))
assert gate["action"]=="WAIT_RENDER"
if os.environ.get("P344_REQUIRE_RUST_GATE"):
    assert gate["authority"]=="RUST_RUNTIME_GATE"
run=new_run(document_id="doc_release",revision=1,plan_sha256="a"*64,archetype="POLISHED_REPORT",config={})
assert verify_run(run)["next_action"]=="STATIC_CRITIQUE"
print("P3.44 release smoke PASS")
