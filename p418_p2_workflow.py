"""P4.18-P2 deterministic, non-mutating workflow preflight.

This module deliberately issues no execution authorization. Approval and durable
idempotency must be implemented by the authenticated server transaction layer.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from p418_product import normalize_document_task

SCHEMA = "chatgpt-web-hwpx-mcp/p4.18-p2/workflow-draft/v1"
MUTATING = frozenset({"CREATE", "EDIT_INTENT", "TEMPLATE_FILL"})
ROLES = frozenset({"TARGET", "REFERENCE", "TEMPLATE"})
MAX_STEPS = 12


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


def _catalog(documents: Sequence[Mapping[str, Any]]) -> dict[str, dict]:
    if isinstance(documents, (str, bytes)) or not isinstance(documents, Sequence):
        raise ValueError("documents must be a sequence")
    if len(documents) > 200:
        raise ValueError("document catalog exceeds 200 entries")
    result: dict[str, dict] = {}
    for document in documents:
        if not isinstance(document, Mapping):
            raise ValueError("catalog entries must be objects")
        identifier = str(document.get("document_id") or "").strip()
        if not identifier or identifier in result:
            raise ValueError("document IDs must be nonempty and unique")
        revision = document.get("revision")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise ValueError("catalog revision must be a nonnegative integer")
        result[identifier] = {"document_id": identifier, "revision": revision}
    return result


def compile_workflow(
    specification: Mapping[str, Any],
    documents: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Compile explicit typed steps; never infer a mutation target by fuzzy title.

    The catalog is a caller-supplied preflight snapshot, *not* proof of ownership
    or revision freshness. The authenticated executor must recheck both.
    """
    if not isinstance(specification, Mapping):
        raise ValueError("specification must be an object")
    allowed = {"steps", "input_bindings"}
    if set(specification) - allowed:
        raise ValueError("unsupported workflow specification fields")
    steps = specification.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
        raise ValueError("steps must contain between 1 and 12 entries")
    catalog = _catalog(documents)
    bindings = specification.get("input_bindings", {})
    if not isinstance(bindings, Mapping):
        raise ValueError("input_bindings must be an object")
    if set(bindings) - ROLES:
        raise ValueError("unsupported input binding roles")
    resolved: dict[str, dict] = {}
    for role, identifier in bindings.items():
        if not isinstance(identifier, str) or identifier not in catalog:
            raise ValueError(f"{role} must identify a catalog document")
        resolved[role] = catalog[identifier]

    compiled: list[dict] = []
    mutations = 0
    for index, entry in enumerate(steps):
        if not isinstance(entry, Mapping) or set(entry) != {"task"}:
            raise ValueError(f"step {index} must contain only a typed task")
        payload = dict(entry["task"]) if isinstance(entry["task"], Mapping) else None
        if payload is None:
            raise ValueError("task must be an object")
        kind = str(payload.get("kind", "")).upper()
        role = {"EDIT_INTENT": "TARGET", "TEMPLATE_FILL": "TEMPLATE"}.get(kind)
        if role and not payload.get("document_id" if role == "TARGET" else "template_document_id"):
            if role not in resolved:
                raise ValueError(f"{kind} requires explicit {role} selection")
            payload["document_id" if role == "TARGET" else "template_document_id"] = resolved[role]["document_id"]
        if kind == "EDIT_INTENT" and payload.get("expected_revision") is None:
            if "TARGET" not in resolved:
                raise ValueError("EDIT_INTENT requires expected_revision")
            payload["expected_revision"] = resolved["TARGET"]["revision"]
        task = normalize_document_task(payload)
        if kind == "EDIT_INTENT":
            found = catalog.get(task["document_id"])
            if found is None or found["revision"] != task["expected_revision"]:
                raise ValueError("target missing or stale in catalog")
        if kind == "TEMPLATE_FILL" and task["template_document_id"] not in catalog:
            raise ValueError("template missing in catalog")
        if kind in MUTATING:
            mutations += 1
        compiled.append({"ordinal": index, "task": task, "effect": "MUTATION" if kind in MUTATING else "READ_ONLY"})
    # Multi-mutation workflows require durable transaction/saga recovery that P2
    # has not yet established; fail closed instead of implying atomicity.
    if mutations > 1:
        raise ValueError("multiple mutations require durable execution coordination")
    draft = {
        "schema": SCHEMA,
        "resolved_inputs": resolved,
        "steps": compiled,
        "mutation_count": mutations,
        "status": "DRAFT_REQUIRES_SERVER_PREVIEW_AND_APPROVAL" if mutations else "READ_ONLY_DRAFT",
        "executable": False,
        "authority": "NON_MUTATING_CALLER_CATALOG_PREFLIGHT_ONLY",
    }
    draft["draft_sha256"] = _digest(draft)
    return draft
