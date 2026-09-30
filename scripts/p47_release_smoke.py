from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from p47_native_authoring import (
    adjudicate_equation_render_evidence,
    authoring_v2_contract,
    compile_unified_authoring_plan,
    equation_render_frontier,
)

contract = authoring_v2_contract()
assert contract["phase"] == "P4.7"
assert contract["product"] == "0.33.0-p4.7"
assert len(contract["high_level_tools"]) == 5
frontier = equation_render_frontier()
assert frontier["production_raw_eqedit"] == "CLOSED"
assert frontier["candidate_count"] >= 8
assert adjudicate_equation_render_evidence(None)["status"] == "WORLD_CONTACT_PENDING"
compiled = compile_unified_authoring_plan({
    "rich_plan": {"sections": [{"blocks": [{"type": "paragraph", "text": "P4.7 smoke"}]}]},
    "native_bundle": {},
})
assert compiled["native_operation_count"] == 0
print("P4.7 render-grounded unified authoring smoke PASS")
