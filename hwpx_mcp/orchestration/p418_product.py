from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

PHASE = "P4.18"
PRODUCT = "0.43.0-p4.18"
TASK_SCHEMA = "chatgpt-web-hwpx-mcp/p4.18/document-task/v1"
CONTRACT_SCHEMA = "chatgpt-web-hwpx-mcp/p4.18/document-agent-contract/v1"

KINDS = {
    "CREATE",
    "EDIT_INTENT",
    "TEMPLATE_FILL",
    "DELIVER",
    "INSPECT",
}
DEFAULT_TTL_SECONDS = 900
MAX_TTL_SECONDS = 3600


def _stable(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: Any) -> str:
    return hashlib.sha256(_stable(value).encode("utf-8")).hexdigest()


def document_agent_contract() -> dict:
    body = {
        "schema": CONTRACT_SCHEMA,
        "phase": PHASE,
        "product": PRODUCT,
        "product_goal": "ONE_PRIMARY_TASK_SURFACE_OVER_VERIFIED_EXISTING_HWPX_CAPABILITIES",
        "primary_tools": [
            "get_p418_document_agent_contract",
            "prepare_p418_document_task",
            "run_p418_document_task",
        ],
        "task_kinds": sorted(KINDS),
        "routing": {
            "CREATE": "P3.37_CREATE_VALIDATE_DELIVER",
            "EDIT_INTENT": "P4.17_INTENT_PLAN_EXECUTE_VERIFY_THEN_DELIVER",
            "TEMPLATE_FILL": "P3.37_TEMPLATE_FILL_VALIDATE_DELIVER",
            "DELIVER": "REVISION_BOUND_DELIVERY_ONLY_NO_MUTATION_REPLAY",
            "INSPECT": "OWNED_DOCUMENT_INSPECTION_NO_MUTATION",
        },
        "llm_boundary": (
            "The MCP server consumes a typed task. Natural-language interpretation is performed "
            "by the calling assistant; the server does not pretend to infer unrestricted prose intent."
        ),
        "safety": {
            "edit_revision_guard": True,
            "delivery_replay_mutation": False,
            "unsupported_task": "ABSTAIN",
            "native_visual_pass_from_caller_metadata": False,
        },
        "user_experience": {
            "normal_create": "one task call returns a native HWPX handoff",
            "normal_edit": "one task call plans, executes, verifies and returns the edited HWPX",
            "normal_template_fill": "one task call clones/fills/validates and returns HWPX",
            "delivery_recovery": "DELIVER reissues a link for an already committed revision",
        },
        "authority": "TASK_ROUTING_AND_COMPOSED_EXISTING_EXECUTION_AUTHORITY",
    }
    body["contract_sha256"] = _sha(body)
    return body


def _bounded_ttl(value: Any) -> int:
    ttl = int(value if value is not None else DEFAULT_TTL_SECONDS)
    if ttl < 60 or ttl > MAX_TTL_SECONDS:
        raise ValueError(f"link_ttl_seconds must be between 60 and {MAX_TTL_SECONDS}")
    return ttl


def _require_mapping(value: Any, field: str, *, nonempty: bool = True) -> dict:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    out = dict(value)
    if nonempty and not out:
        raise ValueError(f"{field} must not be empty")
    return out


def normalize_document_task(task: Mapping[str, Any]) -> dict:
    if not isinstance(task, Mapping):
        raise ValueError("task must be an object")
    raw = dict(task)
    kind = str(raw.get("kind") or "").strip().upper()
    if kind not in KINDS:
        raise ValueError("kind must be one of " + ", ".join(sorted(KINDS)))

    normalized: dict[str, Any] = {
        "schema": TASK_SCHEMA,
        "kind": kind,
        "link_ttl_seconds": _bounded_ttl(raw.get("link_ttl_seconds")),
    }

    if kind == "CREATE":
        normalized.update(
            plan=_require_mapping(raw.get("plan"), "plan"),
            filename=str(raw.get("filename") or "document.hwpx"),
            request_id=str(raw.get("request_id") or ""),
            design_mode=str(raw.get("design_mode") or "AUTO").upper(),
            explicit_tokens=(
                None
                if raw.get("explicit_tokens") is None
                else _require_mapping(raw.get("explicit_tokens"), "explicit_tokens", nonempty=False)
            ),
        )
    elif kind == "EDIT_INTENT":
        document_id = str(raw.get("document_id") or "").strip()
        if not document_id:
            raise ValueError("document_id is required for EDIT_INTENT")
        if raw.get("expected_revision") is None:
            raise ValueError("expected_revision is required for EDIT_INTENT")
        normalized.update(
            document_id=document_id,
            expected_revision=int(raw["expected_revision"]),
            intent=_require_mapping(raw.get("intent"), "intent"),
            reference_document_id=str(raw.get("reference_document_id") or ""),
            reference_transfer=(
                None
                if raw.get("reference_transfer") is None
                else _require_mapping(raw.get("reference_transfer"), "reference_transfer")
            ),
            repair_plan=(
                None
                if raw.get("repair_plan") is None
                else _require_mapping(raw.get("repair_plan"), "repair_plan")
            ),
            replan_intent=(
                None
                if raw.get("replan_intent") is None
                else _require_mapping(raw.get("replan_intent"), "replan_intent")
            ),
            lease_token=str(raw.get("lease_token") or ""),
        )
    elif kind == "TEMPLATE_FILL":
        template_document_id = str(raw.get("template_document_id") or "").strip()
        if not template_document_id:
            raise ValueError("template_document_id is required for TEMPLATE_FILL")
        normalized.update(
            template_document_id=template_document_id,
            values=_require_mapping(raw.get("values"), "values"),
            filename=str(raw.get("filename") or ""),
            request_id=str(raw.get("request_id") or ""),
            require_each=bool(raw.get("require_each", True)),
            require_unique=bool(raw.get("require_unique", False)),
        )
    elif kind == "DELIVER":
        document_id = str(raw.get("document_id") or "").strip()
        if not document_id:
            raise ValueError("document_id is required for DELIVER")
        normalized.update(
            document_id=document_id,
            revision=(None if raw.get("revision") in (None, "") else int(raw["revision"])),
        )
    elif kind == "INSPECT":
        document_id = str(raw.get("document_id") or "").strip()
        if not document_id:
            raise ValueError("document_id is required for INSPECT")
        views = raw.get("views") or ["SUMMARY"]
        if not isinstance(views, list) or not views:
            raise ValueError("views must be a non-empty list")
        admitted = {"SUMMARY", "SEMANTIC_GRAPH", "DOCUMENT_MAP"}
        normalized_views = [str(x).strip().upper() for x in views]
        unknown = sorted(set(normalized_views) - admitted)
        if unknown:
            raise ValueError("unsupported inspect views: " + ", ".join(unknown))
        normalized.update(document_id=document_id, views=normalized_views)

    fingerprint = {k: v for k, v in normalized.items() if k != "task_sha256"}
    normalized["task_sha256"] = _sha(fingerprint)
    return normalized


def prepare_document_task(task: Mapping[str, Any]) -> dict:
    normalized = normalize_document_task(task)
    route = document_agent_contract()["routing"][normalized["kind"]]
    return {
        "schema": "chatgpt-web-hwpx-mcp/p4.18/prepared-task/v1",
        "phase": PHASE,
        "product": PRODUCT,
        "kind": normalized["kind"],
        "route": route,
        "task": normalized,
        "task_sha256": normalized["task_sha256"],
        "mutation_expected": normalized["kind"] in {"CREATE", "EDIT_INTENT", "TEMPLATE_FILL"},
        "native_handoff_expected": normalized["kind"] in {"CREATE", "EDIT_INTENT", "TEMPLATE_FILL", "DELIVER"},
        "authority": "DETERMINISTIC_TASK_ROUTING_NO_MUTATION",
    }
