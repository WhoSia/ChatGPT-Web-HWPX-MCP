from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from p346_mcp import AdapterRegistry
from p346_platform_bridge import (
    platform_contract,
    validate_composition,
    validate_projected_tool_plan,
    validate_projected_tool_sequence,
)

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

derived_sequence = validate_projected_tool_sequence([
    "get_developer_platform_contract",
    "hot_swap_document_host_adapter_profile",
])
assert derived_sequence["typescript"]["effects"] == [
    "READ_ONLY",
    "RUNTIME_CONFIGURATION",
]
assert derived_sequence["rust"]["ok"] is True

derived_plan = validate_projected_tool_plan({
    "schema": "chatgpt-web-hwpx-mcp/p3.46/tool-call-plan/v1",
    "nodes": [
        {"id": "inspect", "tool": "get_developer_platform_contract"},
        {
            "id": "configure",
            "deps": ["inspect"],
            "tool": "hot_swap_document_host_adapter_profile",
        },
    ],
})
assert derived_plan["authority"] == "CONTRACT_DERIVED_CROSS_RUNTIME_TOOL_PLAN_PASS"


def _readonly(**kwargs):
    return {
        "revision_after": int(kwargs["current_revision"]),
        "output_sha256": "a" * 64,
    }


def _mutation(**kwargs):
    return {
        "revision_after": int(kwargs["current_revision"]) + 1,
        "output_sha256": "b" * 64,
    }


registry = AdapterRegistry({
    "DOCUMENT_SNAPSHOT": _readonly,
    "DOCUMENT_TEXT_EDIT": _mutation,
})
doc_a = registry.snapshot("release-a")
swapped = registry.swap(
    "p3.45-compat",
    doc_a["generation"],
    document_id="release-a",
)
assert swapped["active_profile"] == "p3.45-compat"
assert registry.snapshot("release-b")["active_profile"] == "p3.46-guarded"
assert registry.snapshot("release-b")["generation"] == 1
rolled = registry.rollback(
    swapped["generation"],
    document_id="release-a",
)
assert rolled["active_profile"] == "p3.46-guarded"

print("P3.46 release smoke PASS")
