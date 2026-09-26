from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from copy import deepcopy
from typing import Any, Mapping

SCHEMA = "chatgpt-web-hwpx-mcp/p3.44/autonomous-authoring-run/v1"
CONTRACT_SCHEMA = "chatgpt-web-hwpx-mcp/p3.44/autonomous-authoring-contract/v1"
ACTIONS = {"REPAIR", "WAIT_RENDER", "WAIT_HUMAN", "DELIVER", "HOLD"}
STATIC_VERDICTS = {"PASS", "PASS_WITH_WARNINGS", "NEEDS_REPAIR"}
RENDER_REQUIREMENTS = {"REQUIRED", "WHEN_AVAILABLE", "NOT_REQUIRED"}
RENDER_VERDICTS = {"NOT_PROVIDED", "PENDING", "PASS", "PASS_WITH_WARNINGS", "NEEDS_REPAIR", "INVALID"}
HUMAN_REQUIREMENTS = {"REQUIRED", "NOT_REQUIRED"}
HUMAN_VERDICTS = {"PENDING", "PASS", "FAIL"}


def _stable(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: Any) -> str:
    return hashlib.sha256(_stable(value).encode("utf-8")).hexdigest()


def normalize_config(config: Mapping[str, Any] | None = None) -> dict:
    raw = dict(config or {})
    allowed = {
        "max_repair_rounds", "auto_repair", "render_requirement",
        "human_requirement", "delivery_when_ready", "link_ttl_seconds",
    }
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError("unknown P3.44 config fields: " + ",".join(sorted(unknown)))
    max_repairs = int(raw.get("max_repair_rounds", 2))
    if max_repairs < 0 or max_repairs > 3:
        raise ValueError("max_repair_rounds must be between 0 and 3")
    render_requirement = str(raw.get("render_requirement") or "REQUIRED").upper()
    human_requirement = str(raw.get("human_requirement") or "NOT_REQUIRED").upper()
    if render_requirement not in RENDER_REQUIREMENTS:
        raise ValueError("invalid render_requirement")
    if human_requirement not in HUMAN_REQUIREMENTS:
        raise ValueError("invalid human_requirement")
    ttl = int(raw.get("link_ttl_seconds", 900))
    if ttl < 60 or ttl > 900:
        raise ValueError("link_ttl_seconds must be between 60 and 900")
    return {
        "max_repair_rounds": max_repairs,
        "auto_repair": bool(raw.get("auto_repair", True)),
        "render_requirement": render_requirement,
        "human_requirement": human_requirement,
        "delivery_when_ready": bool(raw.get("delivery_when_ready", True)),
        "link_ttl_seconds": ttl,
    }


def autonomous_authoring_contract() -> dict:
    return {
        "schema": CONTRACT_SCHEMA,
        "phase": "P3.44",
        "product_goal": "AUDITABLE_BOUNDED_AUTONOMOUS_PROFESSIONAL_HWPX_AUTHORING",
        "pipeline": [
            "PLAN",
            "COMPOSE",
            "STATIC_CRITIQUE",
            "BOUNDED_REPAIR",
            "WAIT_FOR_RENDER_WORLD_CONTACT",
            "RENDER_CRITIQUE",
            "BOUNDED_REPAIR_AND_RE_RENDER_WHEN_NEEDED",
            "OPTIONAL_HUMAN_GATE",
            "DELIVER",
        ],
        "runtime_language_roles": {
            "rust": "PRODUCTION_REPAIR_DELIVERY_GATE_BINARY",
            "typescript": "INDEPENDENT_STATE_MACHINE_AND_AUTHORBENCH_BLIND_EVALUATOR",
            "python": "HWPX_NATIVE_ADAPTER_BENCHMARK_MATERIALIZER_AND_MCP_BINDING",
            "powershell": "WINDOWS_HANCOM_WORLD_CONTACT",
        },
        "boundedness": {
            "repair_rounds": {"min": 0, "max": 3, "default": 2},
            "no_unbounded_agent_loop": True,
            "render_pause_is_explicit": True,
            "repair_requires_locator_bound_executable_plan": True,
            "delivery_is_terminal_gate": True,
        },
        "evidence_authority": [
            "STRUCTURAL_NATIVE_FACT",
            "STATIC_CRITIQUE",
            "MEASURED_MUTATION_FOOTPRINT",
            "RENDER_OBSERVATION",
            "HANCOM_NATIVE_RENDER_EVIDENCE",
            "HUMAN_VISUAL_REVIEW",
        ],
        "resume_semantics": {
            "persisted_run_receipt": True,
            "render_evidence_invalidated_after_repair": True,
            "stale_run_hash_fails_closed": True,
        },
        "non_claims": [
            "Static PASS is not native-render PASS.",
            "Automated repair does not authorize unsupported narrative mutation.",
            "Delivery is not proof that ChatGPT rendered an attachment card.",
            "Human visual review is not replaced by a machine beauty score.",
        ],
    }


def _reference_decision(snapshot: Mapping[str, Any]) -> dict:
    s = dict(snapshot)
    if not bool(s["policy_ok"]):
        return {"action": "HOLD", "reason": "POLICY_GATE_FAILED"}
    if not bool(s["footprint_ok"]):
        return {"action": "HOLD", "reason": "PRESERVATION_GATE_FAILED"}
    if s["static_verdict"] == "NEEDS_REPAIR":
        if int(s["repairs_used"]) >= int(s["max_repairs"]):
            return {"action": "HOLD", "reason": "REPAIR_LIMIT_EXHAUSTED"}
        if not bool(s["repairable"]):
            return {"action": "HOLD", "reason": "STATIC_REPAIR_GAP"}
        return {"action": "REPAIR", "reason": "STATIC_REPAIR_REQUIRED"}

    render_provided = s["render_verdict"] not in {"NOT_PROVIDED", "PENDING"}
    if s["render_requirement"] == "REQUIRED":
        if not render_provided:
            return {"action": "WAIT_RENDER", "reason": "RENDER_EVIDENCE_REQUIRED"}
        if s["render_verdict"] == "INVALID":
            return {"action": "HOLD", "reason": "RENDER_EVIDENCE_INVALID"}
        if s["render_verdict"] == "NEEDS_REPAIR":
            if int(s["repairs_used"]) >= int(s["max_repairs"]):
                return {"action": "HOLD", "reason": "REPAIR_LIMIT_EXHAUSTED"}
            if not bool(s["repairable"]):
                return {"action": "HOLD", "reason": "RENDER_REPAIR_GAP"}
            return {"action": "REPAIR", "reason": "RENDER_REPAIR_REQUIRED"}
    elif s["render_requirement"] == "WHEN_AVAILABLE" and render_provided:
        if s["render_verdict"] == "INVALID":
            return {"action": "HOLD", "reason": "RENDER_EVIDENCE_INVALID"}
        if s["render_verdict"] == "NEEDS_REPAIR":
            if int(s["repairs_used"]) >= int(s["max_repairs"]):
                return {"action": "HOLD", "reason": "REPAIR_LIMIT_EXHAUSTED"}
            if not bool(s["repairable"]):
                return {"action": "HOLD", "reason": "RENDER_REPAIR_GAP"}
            return {"action": "REPAIR", "reason": "RENDER_REPAIR_REQUIRED"}

    if s["human_requirement"] == "REQUIRED":
        if s["human_verdict"] == "PENDING":
            return {"action": "WAIT_HUMAN", "reason": "HUMAN_REVIEW_REQUIRED"}
        if s["human_verdict"] == "FAIL":
            return {"action": "HOLD", "reason": "HUMAN_REVIEW_FAILED"}
    return {"action": "DELIVER", "reason": "ALL_REQUIRED_GATES_PASS"}


def normalize_gate_snapshot(snapshot: Mapping[str, Any]) -> dict:
    s = dict(snapshot)
    static = str(s.get("static_verdict") or "").upper()
    render_requirement = str(s.get("render_requirement") or "").upper()
    render = str(s.get("render_verdict") or "NOT_PROVIDED").upper()
    human_requirement = str(s.get("human_requirement") or "NOT_REQUIRED").upper()
    human = str(s.get("human_verdict") or "PENDING").upper()
    if static not in STATIC_VERDICTS:
        raise ValueError("invalid static_verdict")
    if render_requirement not in RENDER_REQUIREMENTS or render not in RENDER_VERDICTS:
        raise ValueError("invalid render gate input")
    if human_requirement not in HUMAN_REQUIREMENTS or human not in HUMAN_VERDICTS:
        raise ValueError("invalid human gate input")
    repairs_used = int(s.get("repairs_used", 0))
    max_repairs = int(s.get("max_repairs", 0))
    if repairs_used < 0 or max_repairs < 0 or repairs_used > 3 or max_repairs > 3:
        raise ValueError("repair counters out of bounds")
    return {
        "static_verdict": static,
        "render_requirement": render_requirement,
        "render_verdict": render,
        "repairable": bool(s.get("repairable", False)),
        "repairs_used": repairs_used,
        "max_repairs": max_repairs,
        "policy_ok": bool(s.get("policy_ok", True)),
        "footprint_ok": bool(s.get("footprint_ok", True)),
        "human_requirement": human_requirement,
        "human_verdict": human,
    }


def evaluate_runtime_gate(snapshot: Mapping[str, Any], *, require_rust: bool = False) -> dict:
    s = normalize_gate_snapshot(snapshot)
    binary = os.environ.get("P344_GATE_BIN") or shutil.which("p344-gate")
    if binary:
        args = [
            binary, s["static_verdict"], s["render_requirement"], s["render_verdict"],
            "true" if s["repairable"] else "false", str(s["repairs_used"]), str(s["max_repairs"]),
            "true" if s["policy_ok"] else "false", "true" if s["footprint_ok"] else "false",
            s["human_requirement"], s["human_verdict"],
        ]
        proc = subprocess.run(args, check=True, capture_output=True, text=True, timeout=5)
        raw = proc.stdout.strip()
        action, sep, reason = raw.partition("|")
        if sep != "|" or action not in ACTIONS or not reason:
            raise RuntimeError("invalid p344-gate output")
        return {
            "action": action,
            "reason": reason,
            "authority": "RUST_RUNTIME_GATE",
            "runtime": binary,
            "snapshot_sha256": _sha(s),
        }
    if require_rust:
        raise RuntimeError("P3.44 Rust runtime gate unavailable")
    decision = _reference_decision(s)
    return {
        **decision,
        "authority": "PYTHON_REFERENCE_FALLBACK",
        "runtime": None,
        "snapshot_sha256": _sha(s),
    }


def diagnostic_summary(diagnostic: Mapping[str, Any]) -> dict:
    verdict = str(diagnostic.get("verdict") or "PASS_WITH_WARNINGS").upper()
    if verdict in {"FAIL", "HOLD", "REVIEW_REQUIRED"}:
        verdict = "NEEDS_REPAIR"
    if verdict not in STATIC_VERDICTS:
        verdict = "PASS_WITH_WARNINGS"
    severities = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}
    codes: list[str] = []
    for row in diagnostic.get("findings") or []:
        sev = str((row or {}).get("severity") or "LOW").upper()
        if sev in severities:
            severities[sev] += 1
        code = str((row or {}).get("code") or "")
        if code:
            codes.append(code)
    return {
        "verdict": verdict,
        "finding_count": sum(severities.values()),
        "severity_counts": severities,
        "finding_codes": sorted(codes),
        "diagnostic_sha256": diagnostic.get("diagnostic_sha256") or diagnostic.get("p339_diagnostic_sha256"),
    }


def repair_plan_summary(plan: Mapping[str, Any]) -> dict:
    actions = [row for row in (plan.get("actions") or []) if isinstance(row, Mapping)]
    executable = [row for row in actions if str(row.get("status") or "").upper() == "EXECUTABLE"]
    gaps = [row for row in actions if str(row.get("status") or "").upper() in {"CAPABILITY_GAP", "AGENT_PLAN"}]
    return {
        "action_count": len(actions),
        "executable_count": len(executable),
        "gap_count": len(gaps),
        "repairable": bool(executable),
        "repair_plan_sha256": plan.get("repair_plan_sha256"),
    }


def human_feedback_verdict(rows: list[dict] | None) -> str:
    if not rows:
        return "PENDING"
    statuses = [str((row or {}).get("status") or "").upper() for row in rows]
    if any(x in {"FAIL", "HOLD", "REJECT"} for x in statuses):
        return "FAIL"
    if all(x in {"PASS", "MANUAL_PASS", "PASS_WITH_RESIDUALS", "MANUAL_PASS_WITH_RESIDUAL"} for x in statuses):
        return "PASS"
    return "PENDING"


def _seal_run(run: Mapping[str, Any]) -> dict:
    out = deepcopy(dict(run))
    out.pop("run_sha256", None)
    out["run_sha256"] = _sha(out)
    return out


def new_run(*, document_id: str, revision: int, plan_sha256: str, archetype: str, config: Mapping[str, Any], policy_ok: bool = True) -> dict:
    cfg = normalize_config(config)
    seed = {
        "document_id": document_id,
        "revision": int(revision),
        "plan_sha256": str(plan_sha256 or ""),
        "archetype": str(archetype or "POLISHED_REPORT").upper(),
        "config": cfg,
    }
    run = {
        "schema": SCHEMA,
        "phase": "P3.44",
        "run_id": "p344_" + _sha(seed)[:24],
        **seed,
        "policy_ok": bool(policy_ok),
        "footprint_ok": True,
        "repair_rounds": 0,
        "render_cycle": 0,
        "status": "COMPOSED",
        "next_action": "STATIC_CRITIQUE",
        "events": [{
            "stage": "COMPOSE",
            "revision": int(revision),
            "evidence": {"plan_sha256": str(plan_sha256 or "")},
        }],
        "latest_static": None,
        "latest_render": None,
        "latest_repair_plan": None,
        "latest_gate": None,
        "authority": "AUDITABLE_AUTONOMOUS_RUN_NOT_RENDER_SUCCESS_CLAIM",
    }
    return _seal_run(run)


def append_event(run: Mapping[str, Any], *, stage: str, revision: int, evidence: Mapping[str, Any]) -> dict:
    out = deepcopy(dict(run))
    out.pop("run_sha256", None)
    events = list(out.get("events") or [])
    if len(events) >= 40:
        raise ValueError("P3.44 run event bound exceeded")
    events.append({"stage": str(stage), "revision": int(revision), "evidence": dict(evidence)})
    out["events"] = events
    out["revision"] = int(revision)
    return _seal_run(out)


def verify_run(run: Mapping[str, Any]) -> dict:
    supplied = str(run.get("run_sha256") or "")
    resealed = _seal_run(run)
    if supplied != resealed["run_sha256"]:
        raise ValueError("P3.44 run receipt hash mismatch")
    if run.get("schema") != SCHEMA or run.get("phase") != "P3.44":
        raise ValueError("invalid P3.44 run receipt")
    return deepcopy(dict(run))
