from __future__ import annotations

import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from p345_runtime_bridge import compile_ir,create_run,runtime_contract,transition,verify_replay

contract=runtime_contract()
assert contract["phase"]=="P3.45"
assert contract["language_authority"]["typescript"]=="PRIMARY_IR_COMPILER_SCHEDULER_AND_RUNTIME_STATE_MACHINE"
ir={
    "schema":"chatgpt-web-hwpx-mcp/p3.45/authoring-ir/v1",
    "ir_id":"release-smoke",
    "document_id":"doc_release",
    "base_revision":1,
    "nodes":[
        {"id":"snapshot","kind":"document.snapshot","inputs":{"view":"document"},"reusable":True},
        {"id":"format","kind":"document.format.edit","deps":["snapshot"],"inputs":{"operations":[]}},
        {"id":"render","kind":"document.render.evidence","deps":["format"],"inputs":{"renderer":"HANCOM"}},
    ],
}
compiled=compile_ir({"ir":ir})
assert compiled["actions"]=={"snapshot":"EXECUTE","format":"EXECUTE","render":"WAIT_EXTERNAL"}
state=create_run(compiled)
verify_replay(state)
state=transition(state,{"type":"START_NODE","node_id":"snapshot"})
state=transition(state,{"type":"COMMIT_NODE","node_id":"snapshot","revision":1,"output_sha256":"a"*64,"receipt_sha256":"1"*64})
verify_replay(state)
print("P3.45 release smoke PASS")
