from __future__ import annotations

import os
from pathlib import Path

import pytest

from p344_autonomous_authoring import (
    autonomous_authoring_contract,
    diagnostic_summary,
    evaluate_runtime_gate,
    human_feedback_verdict,
    new_run,
    normalize_config,
    repair_plan_summary,
    verify_run,
)


def test_contract_is_polyglot_and_bounded():
    c = autonomous_authoring_contract()
    assert c["phase"] == "P3.44"
    assert c["runtime_language_roles"]["rust"] == "PRODUCTION_REPAIR_DELIVERY_GATE_BINARY"
    assert c["boundedness"]["repair_rounds"]["max"] == 3
    assert c["boundedness"]["no_unbounded_agent_loop"] is True


def test_reference_gate_waits_for_render_and_fails_closed():
    base = {
        "static_verdict": "PASS",
        "render_requirement": "REQUIRED",
        "render_verdict": "NOT_PROVIDED",
        "repairable": False,
        "repairs_used": 0,
        "max_repairs": 2,
        "policy_ok": True,
        "footprint_ok": True,
        "human_requirement": "NOT_REQUIRED",
        "human_verdict": "PENDING",
    }
    d = evaluate_runtime_gate(base)
    assert d["action"] == "WAIT_RENDER"
    bad = dict(base, policy_ok=False)
    assert evaluate_runtime_gate(bad)["reason"] == "POLICY_GATE_FAILED"


def test_run_hash_and_summaries():
    run = new_run(document_id="doc_x", revision=1, plan_sha256="a"*64, archetype="POLISHED_REPORT", config={})
    assert verify_run(run)["run_id"].startswith("p344_")
    broken = dict(run, revision=2)
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_run(broken)

    diag = diagnostic_summary({"verdict":"NEEDS_REPAIR","findings":[{"code":"X","severity":"HIGH"}]})
    assert diag["severity_counts"]["HIGH"] == 1
    plan = repair_plan_summary({"actions":[{"status":"EXECUTABLE"},{"status":"AGENT_PLAN"}]})
    assert plan["repairable"] and plan["gap_count"] == 1
    assert human_feedback_verdict([{"status":"MANUAL_PASS_WITH_RESIDUAL"}]) == "PASS"


def test_config_bounds():
    assert normalize_config({})["render_requirement"] == "REQUIRED"
    with pytest.raises(ValueError):
        normalize_config({"max_repair_rounds": 4})
