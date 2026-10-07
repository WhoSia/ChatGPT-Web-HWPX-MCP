from p418_product import document_agent_contract, prepare_document_task

contract = document_agent_contract()
assert contract["phase"] == "P4.18"
assert contract["product"] == "0.43.0-p4.18"
assert contract["product_goal"] == "ONE_PRIMARY_TASK_SURFACE_OVER_VERIFIED_EXISTING_HWPX_CAPABILITIES"
assert set(contract["task_kinds"]) == {"CREATE", "EDIT_INTENT", "TEMPLATE_FILL", "DELIVER", "INSPECT"}

prepared = prepare_document_task({
    "kind": "DELIVER",
    "document_id": "release-smoke-document",
    "revision": 1,
})
assert prepared["route"] == "REVISION_BOUND_DELIVERY_ONLY_NO_MUTATION_REPLAY"
assert prepared["mutation_expected"] is False
assert prepared["native_handoff_expected"] is True

prepared_edit = prepare_document_task({
    "kind": "EDIT_INTENT",
    "document_id": "release-smoke-document",
    "expected_revision": 1,
    "intent": {
        "actions": [
            {"action": "replace_role_text", "role": "TITLE", "text": "P4.18"}
        ]
    },
})
assert prepared_edit["route"] == "P4.17_INTENT_PLAN_EXECUTE_VERIFY_THEN_DELIVER"
assert prepared_edit["mutation_expected"] is True
print("P4.18 end-user document agent release smoke PASS")
