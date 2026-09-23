from __future__ import annotations

import hashlib
import json
from typing import Any

SCHEMA = "chatgpt-web-hwpx-mcp/rare-feature-registry/p3.34/v1"

EVIDENCE_KEYS = (
    "semantic_contract",
    "structural_fixture",
    "native_open_resave_or_render",
    "family_regression",
    "primary_delivery_regression",
)

_FEATURES = {
    "column_insertion": {
        "family": "tables",
        "ancestry": ["P2.7", "P2.8", "P3.23", "P3.34-R1"],
        "state": "BOUNDED_PRODUCTION_AUTHORITY",
        "authority": "COUNT1_LEFT_RIGHT_NATIVE_COLUMN_INSERTION",
        "reason": (
            "Hancom 13.0.0.3622 native before/after evidence plus implementation-generated "
            "open-save round-trip established count=1 LEFT/RIGHT insertion, anchor-width cloning, "
            "table-width growth, colAddr shifting, and crossing horizontal colSpan extension. "
            "count>1, vertical-merge, and nested-table cases remain fail-closed."
        ),
        "bounds": {
            "operation": "insert_column_native_bounded",
            "directions": ["LEFT", "RIGHT"],
            "count": 1,
            "vertical_merge": False,
            "nested_table": False
        },
    },
    "tracked_change_resolution": {
        "family": "review",
        "ancestry": ["P3.22", "P3.34-R2"],
        "state": "BOUNDED_PRODUCTION_AUTHORITY",
        "authority": "UNPROTECTED_WHOLE_DOCUMENT_ACCEPT_REJECT_ALL",
        "reason": (
            "Hancom 13.0.0.3622 native resolution evidence (6/6), protected-boundary evidence "
            "(3/3), implementation-generated open/save round-trip (4/4), family regression, "
            "OAuth/Docker, and inherited P3.33 delivery regression establish bounded whole-document "
            "Accept All / Reject All for simple unprotected P3.22-authored Insert/Delete/Replace. "
            "Protected/password resolution, selective per-change resolution, mixed inline tracked "
            "markup, and protection authoring remain fail-closed."
        ),
        "bounds": {
            "operations": [
                "accept_all_tracked_changes",
                "reject_all_tracked_changes"
            ],
            "scope": "whole-document",
            "protected_documents": False,
            "header_change_types": ["INSERT", "DELETE"],
            "simple_direct_hp_t_markers_only": True,
            "selective_per_change": False,
            "protection_authoring": False,
        },
    },
    "existing_group_ungroup": {
        "family": "drawing",
        "ancestry": ["P3.25", "P3.27", "P3.34-R3"],
        "state": "NATIVE_SEMANTICS_PASS_IMPLEMENTATION_ROUNDTRIP_REQUIRED",
        "authority": "NEW_GROUP_AUTHORING_ONLY",
        "reason": (
            "Hancom native evidence establishes bbox-origin grouping and group-origin + child-local "
            "ungroup rebasing for unrotated shared-anchor rect/ellipse objects. A bounded candidate "
            "implementation exists, but production authority remains closed until implementation-generated "
            "Hancom open/save passes. Rotation, scaling, flipping, mixed anchors, nested groups, inline objects, "
            "and other drawing families remain fail-closed."
        ),
        "active_probe": {
            "group_case_passed": 1,
            "ungroup_cases_passed": 2,
            "candidate_scope": "exactly two unrotated floating rect/ellipse objects with one shared anchor/frame",
            "production_group_ungroup_authority": False,
        },
    },
    "native_callout_autoshape": {
        "family": "drawing",
        "ancestry": ["P3.25", "P3.26"],
        "state": "NATIVE_EVIDENCE_REQUIRED",
        "authority": "NONE",
        "reason": (
            "Generic low-level shape escape hatches are unsafe without mandatory-child and "
            "Hancom acceptance evidence; dedicated known-safe primitives remain preferred."
        ),
    },
    "smart_connectline": {
        "family": "drawing",
        "ancestry": ["P3.26", "P3.29"],
        "state": "BLOCKED_SEMANTIC_AMBIGUITY",
        "authority": "PRESERVE_ONLY",
        "reason": (
            "Upstream DEV-013 shows anchored hp:connectLine geometry carries subjectIDRef plus "
            "nontrivial offset/size/transform relationships that cannot be reconstructed from "
            "the available clean sample; static managed edges remain the production contract."
        ),
    },
    "polygon_preserving_resize": {
        "family": "drawing",
        "ancestry": ["P3.29"],
        "state": "NATIVE_EVIDENCE_REQUIRED",
        "authority": "MOVE_AND_STYLE_ONLY",
        "reason": (
            "Changing bbox/sz alone does not rebase polygon point geometry. Promotion requires "
            "a measured point-transform rule and reopen/render evidence."
        ),
    },
    "mixed_run_shape_text": {
        "family": "diagram",
        "ancestry": ["P3.28", "P3.29"],
        "state": "NATIVE_EVIDENCE_REQUIRED",
        "authority": "PLAIN_SHAPE_LABEL_ONLY",
        "reason": (
            "Current managed labels intentionally use bounded plain text. Rich mixed-run shape "
            "text needs preservation and edit-locality evidence before authoring promotion."
        ),
    },
    "occupied_name_carrier_override": {
        "family": "brownfield",
        "ancestry": ["P3.29", "P3.32"],
        "state": "SEMANTIC_EVIDENCE_REQUIRED",
        "authority": "FAIL_CLOSED",
        "reason": (
            "P3.29 identity uses the native name carrier. Overwriting an occupied carrier can "
            "destroy pre-existing semantics, so adoption remains fail-closed."
        ),
    },
    "cross_anchor_adoption": {
        "family": "brownfield",
        "ancestry": ["P3.32"],
        "state": "SEMANTIC_AND_NATIVE_EVIDENCE_REQUIRED",
        "authority": "SAME_ANCHOR_ONLY",
        "reason": (
            "Brownfield adoption is currently bounded to evidence-local topology. Cross-anchor "
            "ownership requires an explicit scope and movement/reflow contract."
        ),
    },
    "parallel_managed_edges": {
        "family": "diagram",
        "ancestry": ["P3.29", "P3.32"],
        "state": "IDENTITY_EVIDENCE_REQUIRED",
        "authority": "SINGLE_RELATION_PER_ENDPOINT_PAIR",
        "reason": (
            "Current static-edge reconstruction identifies relations by exact endpoint centers. "
            "Parallel edges require durable edge identity independent of that pair."
        ),
    },
}

UX_GUARD = {
    "phase": "P3.34",
    "policy": "PERIODIC_PRODUCT_UX_SMOKE",
    "cadence": [
        "every production phase before closure",
        "after plugin/package schema changes",
        "after ChatGPT host/plugin UX changes",
        "after delivery-contract changes",
    ],
    "checks": [
        "plugin/package import or connection path still succeeds when host supports it",
        "production MCP discovery/OAuth boundary passes",
        "create-or-edit then validate then deliver_document returns revision-bound HWPX",
        "downloaded bytes match the signed revision receipt",
        "periodic Hancom open-resave specimen remains structurally valid",
    ],
    "non_blocking_host_residuals": [
        "existing chat session may cache an older tool catalog",
        "native attachment-card rendering is host behavior and must be observed separately",
    ],
}


def _sha(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def rare_feature_registry() -> dict:
    features = {key: dict(value) for key, value in sorted(_FEATURES.items())}
    payload = {
        "schema": SCHEMA,
        "phase": "P3.34",
        "authority": "EVIDENCE_GATED_REGISTRY_ONLY",
        "features": features,
        "promotion_evidence_keys": list(EVIDENCE_KEYS),
        "ux_guard": dict(UX_GUARD),
    }
    payload["registry_sha256"] = _sha(payload)
    return payload


def evaluate_rare_feature(feature: str, evidence: dict | None = None) -> dict:
    key = str(feature or "").strip()
    if key not in _FEATURES:
        raise ValueError(f"Unknown rare feature lane: {key}")
    spec = dict(_FEATURES[key])
    supplied = evidence if isinstance(evidence, dict) else {}
    evidence_map = {name: bool(supplied.get(name, False)) for name in EVIDENCE_KEYS}
    missing = [name for name, passed in evidence_map.items() if not passed]
    blocked = spec["state"] == "BLOCKED_SEMANTIC_AMBIGUITY"
    already_promoted = spec["state"] == "BOUNDED_PRODUCTION_AUTHORITY"
    ready = not blocked and not already_promoted and not missing
    result = {
        "schema": SCHEMA,
        "phase": "P3.34",
        "feature": key,
        "family": spec["family"],
        "baseline_state": spec["state"],
        "baseline_authority": spec["authority"],
        "evidence": evidence_map,
        "missing_evidence": [] if already_promoted else missing,
        "promotion_ready": ready,
        "verdict": (
            "ALREADY_PROMOTED_BOUNDED"
            if already_promoted
            else (
                "BLOCKED_SEMANTIC_AMBIGUITY"
                if blocked
                else ("READY_FOR_BOUNDED_PROMOTION" if ready else "EVIDENCE_INCOMPLETE")
            )
        ),
        "reason": spec["reason"],
    }
    result["evaluation_sha256"] = _sha(result)
    return result


def plan_rare_feature_promotion(feature: str, evidence: dict) -> dict:
    evaluated = evaluate_rare_feature(feature, evidence)
    if not evaluated["promotion_ready"]:
        raise ValueError(
            f"Rare feature is not promotion-ready: {evaluated['verdict']}; "
            f"missing={evaluated['missing_evidence']}"
        )
    plan = {
        "schema": SCHEMA,
        "phase": "P3.34",
        "feature": evaluated["feature"],
        "family": evaluated["family"],
        "source_evaluation_sha256": evaluated["evaluation_sha256"],
        "required_next_step": (
            "Implement only the bounded family operation covered by this evidence, then rerun "
            "family regression + OAuth/Docker + P3.33 delivery UX smoke before authority changes."
        ),
        "authority_change": "NOT_APPLIED_BY_THIS_PLAN",
    }
    plan["promotion_plan_sha256"] = _sha(plan)
    return plan


def ux_regression_contract() -> dict:
    payload = {"schema": SCHEMA, **UX_GUARD}
    payload["ux_guard_sha256"] = _sha(payload)
    return payload
