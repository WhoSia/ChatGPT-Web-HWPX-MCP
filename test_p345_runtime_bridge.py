from __future__ import annotations

from p345_runtime_bridge import (
    compile_ir,
    create_run,
    observability,
    prior_snapshot_from_state,
    runtime_contract,
    time_travel,
    transition,
    verify_replay,
)


def _ir(base_revision: int = 1) -> dict:
    return {
        "schema":"chatgpt-web-hwpx-mcp/p3.45/authoring-ir/v1",
        "ir_id":"pytest-runtime",
        "document_id":"doc_test",
        "base_revision":base_revision,
        "nodes":[
            {"id":"snapshot","kind":"document.snapshot","inputs":{"view":"document"},"reusable":True},
            {"id":"format","kind":"document.format.edit","deps":["snapshot"],"inputs":{"operations":[]}},
        ],
    }


def test_runtime_bridge_roundtrip_and_incremental_reuse():
    assert runtime_contract()["phase"]=="P3.45"
    compiled=compile_ir({"ir":_ir()})
    state=create_run(compiled)
    state=transition(state,{"type":"START_NODE","node_id":"snapshot"})
    state=transition(state,{"type":"COMMIT_NODE","node_id":"snapshot","revision":1,"output_sha256":"a"*64,"receipt_sha256":"1"*64})
    state=transition(state,{"type":"START_NODE","node_id":"format"})
    state=transition(state,{"type":"COMMIT_NODE","node_id":"format","revision":2,"output_sha256":"b"*64,"receipt_sha256":"2"*64})
    state=transition(state,{"type":"COMPLETE_RUN"})
    verified=verify_replay(state)
    assert verified["completed"] is True
    assert time_travel(state,3)["node_states"]["snapshot"]=="COMMITTED"
    assert observability(state)["committed_nodes"]==2
    prior=prior_snapshot_from_state(state)
    second=compile_ir({"ir":_ir(2),"prior_snapshot":prior})
    assert second["actions"]["snapshot"]=="REUSE"
    assert second["actions"]["format"]=="EXECUTE"
