from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from p346_platform_bridge import platform_contract, validate_composition

contract = platform_contract()
assert contract["phase"] == "P3.46"
assert contract["product"] == "0.23.0-p3.46"
assert contract["extensions"]["arbitrary_in_process_loading"] is False
assert contract["extensions"]["wasm_linear_memory_allowed"] is False
assert contract["extensions"]["wasm_tables_allowed"] is False
assert contract["extensions"]["parent_process_timeout"] is True
assert contract["hot_swap"]["rollback"] is True
assert contract["hot_swap"]["cross_document_leakage"] is False
assert "RUNTIME_CONFIGURATION" in contract["effect_types"]

plan = {
    "schema": "chatgpt-web-hwpx-mcp/p3.46/effect-plan/v1",
    "nodes": [
        {"id": "inspect", "effect": "READ_ONLY", "action": "EXECUTE"},
        {"id": "mutate", "deps": ["inspect"], "effect": "DOCUMENT_MUTATION", "action": "EXECUTE"},
        {"id": "deliver", "deps": ["mutate"], "effect": "DELIVERY", "action": "EXECUTE"},
    ],
}
receipt = validate_composition(plan)
assert receipt["authority"] == "CROSS_RUNTIME_EFFECT_PLAN_PASS"
print("P3.46 release smoke PASS")
