from __future__ import annotations

import hashlib
import json
from typing import Any

from hwpx_mcp.orchestration.p338_rich_builder import compile_rich_document_plan

PHASE = "P4.7"
PRODUCT = "0.33.0-p4.7"
CAPTURE_SCHEMA = "chatgpt-web-hwpx-mcp/p47/equation-world-contact/v1"

_CANDIDATES = {
    "roman": {
        "intent": "ROMAN_TEXT_STYLE",
        "control_script": "ABC+xyz",
        "candidate_script": "rm {ABC+xyz}",
        "documentation": "HANCOM_OFFICIAL_FONT_COMMAND",
        "syntax_authority": "DOCUMENTED",
        "promotion_target": None,
    },
    "bold": {
        "intent": "BOLD_MATH_STYLE",
        "control_script": "x+y",
        "candidate_script": "bold {x+y}",
        "documentation": "HANCOM_OFFICIAL_FONT_COMMAND",
        "syntax_authority": "DOCUMENTED",
        "promotion_target": r"\mathbf",
    },
    "roman_bold": {
        "intent": "ROMAN_BOLD_STYLE",
        "control_script": "ABC+xyz",
        "candidate_script": "rmbold {ABC+xyz}",
        "documentation": "HANCOM_OFFICIAL_FONT_COMMAND",
        "syntax_authority": "DOCUMENTED",
        "promotion_target": None,
    },
    "color": {
        "intent": "LOCAL_EQUATION_COLOR",
        "control_script": "{3} over {4}",
        "candidate_script": "COLOR {255,0,0}{3} over {COLOR {0,0,255}{4}}",
        "documentation": "HANCOM_OFFICIAL_COLOR_EXAMPLE",
        "syntax_authority": "DOCUMENTED_EXAMPLE",
        "promotion_target": None,
    },
    "pile": {
        "intent": "CENTER_VERTICAL_PILE",
        "control_script": "x=1 # y=2",
        "candidate_script": "PILE {x=1 # y=2}",
        "documentation": "HANCOM_OFFICIAL_COMMAND",
        "syntax_authority": "DOCUMENTED_COMMAND_BOUNDED_SYNTAX_HYPOTHESIS",
        "promotion_target": None,
    },
    "lpile": {
        "intent": "LEFT_VERTICAL_PILE",
        "control_script": "x=1 # yyyy=2",
        "candidate_script": "LPILE {x=1 # yyyy=2}",
        "documentation": "HANCOM_OFFICIAL_COMMAND",
        "syntax_authority": "DOCUMENTED_COMMAND_BOUNDED_SYNTAX_HYPOTHESIS",
        "promotion_target": None,
    },
    "rpile": {
        "intent": "RIGHT_VERTICAL_PILE",
        "control_script": "x=1 # yyyy=2",
        "candidate_script": "RPILE {x=1 # yyyy=2}",
        "documentation": "HANCOM_OFFICIAL_COMMAND",
        "syntax_authority": "DOCUMENTED_COMMAND_BOUNDED_SYNTAX_HYPOTHESIS",
        "promotion_target": None,
    },
    "eqalign": {
        "intent": "ALIGNMENT_MARK_COLUMN_ALIGNMENT",
        "control_script": "x=1 # yyyy=22",
        "candidate_script": "EQALIGN {x&=1 # yyyy&=22}",
        "documentation": "HANCOM_OFFICIAL_EQALIGN_DESCRIPTION",
        "syntax_authority": "DOCUMENTED_COMMAND_BOUNDED_SYNTAX_HYPOTHESIS",
        "promotion_target": "LATEX_ALIGN_FAMILY",
    },
}


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def equation_render_frontier() -> dict:
    rows = []
    for candidate_id, raw in _CANDIDATES.items():
        row = {"candidate_id": candidate_id, **raw}
        row["candidate_sha256"] = _sha(row)
        row["production_authoring_status"] = "NOT_PROMOTED"
        row["world_contact_status"] = "PENDING_NATIVE_HANCOM_CAPTURE"
        rows.append(row)
    return {
        "phase": PHASE,
        "product": PRODUCT,
        "schema": CAPTURE_SCHEMA,
        "candidates": rows,
        "candidate_count": len(rows),
        "policy": "DOCUMENTATION_CREATES_TESTABLE_CANDIDATE_NOT_AUTHORING_AUTHORITY",
        "production_raw_eqedit": "CLOSED",
        "frontier_sha256": _sha(rows),
    }


def capture_pack_contract() -> dict:
    frontier = equation_render_frontier()
    fixtures = []
    for row in frontier["candidates"]:
        for variant in ("control", "candidate"):
            fixtures.append({
                "fixture_id": f"p47-{row['candidate_id']}-{variant}",
                "candidate_id": row["candidate_id"],
                "variant": variant,
                "eqedit_script": row[f"{variant}_script"],
                "script_sha256": hashlib.sha256(row[f"{variant}_script"].encode("utf-8")).hexdigest(),
            })
    return {
        "schema": CAPTURE_SCHEMA,
        "phase": PHASE,
        "product": PRODUCT,
        "fixtures": fixtures,
        "fixture_count": len(fixtures),
        "required_native_receipt": {
            "renderer_name": "Hancom Hangul",
            "hancom_native": True,
            "windows": True,
            "executable_sha256_required": True,
            "pdf_sha256_required_per_fixture": True,
            "source_hwpx_sha256_required_per_fixture": True,
        },
        "required_candidate_adjudication": [
            "export_succeeded",
            "candidate_visual_difference_observed",
            "semantic_intent_match",
            "no_clipping_or_corruption",
            "human_visual_status",
        ],
        "authority": "CAPTURE_PACKET_ONLY_NO_PROMOTION",
        "capture_pack_sha256": _sha(fixtures),
    }


def adjudicate_equation_render_evidence(receipt: dict | None) -> dict:
    frontier = equation_render_frontier()
    if not receipt:
        return {
            "phase": PHASE,
            "product": PRODUCT,
            "status": "WORLD_CONTACT_PENDING",
            "promotion_eligible": [],
            "held": [row["candidate_id"] for row in frontier["candidates"]],
            "authority": "NO_NATIVE_RECEIPT_NO_PROMOTION",
        }
    if not isinstance(receipt, dict):
        raise ValueError("receipt must be an object")
    renderer = receipt.get("renderer") or {}
    if not renderer.get("hancom_native") or "windows" not in str(renderer.get("os") or "").lower():
        raise ValueError("P4.7 render receipt must be Hancom-native on Windows")
    exe = str(renderer.get("executable_sha256") or "").lower()
    if len(exe) != 64:
        raise ValueError("renderer executable_sha256 is required")
    if str(receipt.get("frontier_sha256") or "") != frontier["frontier_sha256"]:
        raise ValueError("P4.7 render receipt frontier hash mismatch")
    rows = receipt.get("candidates")
    if not isinstance(rows, list):
        raise ValueError("receipt.candidates must be a list")
    by_id = {str(x.get("candidate_id")): x for x in rows if isinstance(x, dict)}
    promoted, held, decisions = [], [], []
    for spec in frontier["candidates"]:
        cid = spec["candidate_id"]
        row = by_id.get(cid)
        if row is None:
            held.append(cid)
            decisions.append({"candidate_id": cid, "decision": "HOLD_MISSING_NATIVE_EVIDENCE"})
            continue
        required_true = (
            bool(row.get("export_succeeded"))
            and bool(row.get("candidate_visual_difference_observed"))
            and bool(row.get("semantic_intent_match"))
            and bool(row.get("no_clipping_or_corruption"))
        )
        human = str(row.get("human_visual_status") or "").upper()
        hashes_ok = all(
            len(str(row.get(k) or "").lower()) == 64
            for k in ("control_hwpx_sha256", "candidate_hwpx_sha256", "control_pdf_sha256", "candidate_pdf_sha256")
        )
        if required_true and hashes_ok and human in {"PASS", "PASS_WITH_RESIDUALS"}:
            promoted.append(cid)
            decisions.append({"candidate_id": cid, "decision": "PROMOTION_ELIGIBLE", "promotion_target": spec.get("promotion_target")})
        else:
            held.append(cid)
            decisions.append({"candidate_id": cid, "decision": "HOLD_EVIDENCE_INCOMPLETE_OR_NEGATIVE", "human_visual_status": human or "PENDING"})
    return {
        "phase": PHASE,
        "product": PRODUCT,
        "status": "ADJUDICATED",
        "promotion_eligible": promoted,
        "held": held,
        "decisions": decisions,
        "promotion_requires_code_change": True,
        "authority": "NATIVE_RENDER_PLUS_HUMAN_EVIDENCE_ADJUDICATION_ONLY",
        "adjudication_sha256": _sha(decisions),
    }


def compile_unified_authoring_plan(spec: dict) -> dict:
    if not isinstance(spec, dict):
        raise ValueError("spec must be an object")
    rich_plan = spec.get("rich_plan")
    if not isinstance(rich_plan, dict):
        raise ValueError("spec.rich_plan must be an object")
    native_bundle = spec.get("native_bundle") or {}
    if not isinstance(native_bundle, dict):
        raise ValueError("spec.native_bundle must be an object")
    compiled_rich = compile_rich_document_plan(rich_plan)
    native_count = sum(len(native_bundle.get(k) or []) for k in ("equations", "tables", "drawings"))
    if native_count > 80:
        raise ValueError("native bundle exceeds P4.6 operation bound")
    receipt = {
        "phase": PHASE,
        "product": PRODUCT,
        "rich": compiled_rich,
        "native_bundle": native_bundle,
        "native_operation_count": native_count,
        "creation_semantics": "PRIVATE_RICH_COMPOSE_THEN_NATIVE_MUTATE_THEN_VALIDATE_THEN_REVISION_1_COMMIT",
        "existing_document_semantics": "P4.6_ONE_CALL_ONE_REVISION",
        "authority": "UNIFIED_PLAN_NOT_YET_MUTATION",
    }
    receipt["unified_plan_sha256"] = _sha({
        "rich_plan_sha256": compiled_rich["plan_sha256"],
        "native_bundle": native_bundle,
    })
    return receipt


def human_visual_benchmark_contract() -> dict:
    return {
        "phase": PHASE,
        "product": PRODUCT,
        "axes": [
            "equation_legibility",
            "math_style_semantic_match",
            "alignment_intent_match",
            "table_scanability",
            "drawing_integration",
            "page_rhythm_and_density",
            "no_overlap_or_clipping",
        ],
        "allowed_status": ["PASS", "PASS_WITH_RESIDUALS", "FAIL", "PENDING"],
        "blind_packet_rule": "HUMAN_REVIEW_DOES_NOT_RECEIVE_EXPECTED_WINNER",
        "overall_rule": "NO_NUMERIC_BEAUTY_SCORE_EACH_AXIS_RETAINS_OWN_VERDICT",
        "authority": "HUMAN_VISUAL_EVIDENCE_SEPARATE_FROM_PACKAGE_AND_RENDER_EVIDENCE",
    }


def onboarding_contract() -> dict:
    return {
        "phase": PHASE,
        "product": PRODUCT,
        "goal": "CONNECT_TO_FIRST_NATIVE_HWPX_WITH_MINIMAL_TOOL_DISCOVERY",
        "steps": [
            {"step": 1, "action": "CONNECT_REMOTE_MCP", "evidence": "OAuth protected-resource discovery"},
            {"step": 2, "action": "CALL_get_authoring_v2_contract", "evidence": "capability and unsupported-semantics boundary"},
            {"step": 3, "action": "CALL_create_unified_document_and_deliver", "evidence": "revision-bound downloadable HWPX"},
        ],
        "recovery": {
            "delivery_failure_after_commit": "CALL deliver_document DO_NOT REPEAT mutation",
            "unsupported_equation": "PRESERVE_SOURCE_AND_REPORT_TYPED_ABSTENTION",
        },
        "authority": "ONBOARDING_GUIDANCE_DOES_NOT_BYPASS_OAUTH_OR_EVIDENCE_GATES",
    }


def authoring_v2_contract() -> dict:
    return {
        "phase": PHASE,
        "product": PRODUCT,
        "purpose": "RENDER_GROUNDED_NATIVE_AUTHORING_AND_ONE_PLAN_USER_EXPERIENCE",
        "high_level_tools": [
            "get_authoring_v2_contract",
            "inspect_equation_render_frontier",
            "adjudicate_equation_render_evidence",
            "compile_unified_authoring_plan",
            "create_unified_document_and_deliver",
        ],
        "equation_frontier": equation_render_frontier(),
        "human_visual_benchmark": human_visual_benchmark_contract(),
        "onboarding": onboarding_contract(),
        "invariants": [
            "RAW_EQEDIT_PRODUCTION_GATE_REMAINS_CLOSED",
            "DOCUMENTED_COMMAND_NOT_EQUAL_RENDER_CERTIFIED_AUTHORING",
            "NATIVE_RENDER_NOT_EQUAL_HUMAN_VISUAL_PASS",
            "UNIFIED_NEW_DOCUMENT_COMMITS_ONCE_AT_REVISION_1",
            "UNSUPPORTED_MATH_REMAINS_TYPED_ABSTENTION",
        ],
    }
