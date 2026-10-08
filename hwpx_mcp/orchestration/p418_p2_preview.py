"""P4.18-P2 preview and correction contracts; never grants execution permission.

This pure module is intentionally independent of the server's durable approval store.
All input revision snapshots are *untrusted* until rechecked against owned custody.
"""
from __future__ import annotations

from copy import deepcopy
from collections.abc import Mapping, Sequence
from typing import Any

from hwpx_mcp.orchestration.p418_p2_workflow import _digest, compile_workflow

PREVIEW_SCHEMA = "chatgpt-web-hwpx-mcp/p4.18-p2/preview/v1"
MAX_CORRECTIONS = 16
MAX_PATH_DEPTH = 12


def preview_workflow(draft: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(draft, Mapping):
        raise ValueError("draft must be an object")
    body = dict(draft)
    digest = body.pop("draft_sha256", None)
    if not isinstance(digest, str) or digest != _digest(body):
        raise ValueError("draft integrity check failed")
    if body.get("executable") is not False:
        raise ValueError("draft cannot be executable")
    steps = body.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("draft steps required")
    effects = []
    for step in steps:
        if not isinstance(step, dict) or step.get("effect") not in {"MUTATION", "READ_ONLY"}:
            raise ValueError("invalid step effect")
        task = step.get("task")
        if not isinstance(task, dict) or "kind" not in task:
            raise ValueError("invalid normalized task")
        effects.append({"ordinal": step["ordinal"], "kind": task["kind"], "effect": step["effect"],
                        "document_id": task.get("document_id") or task.get("template_document_id") or ""})
    receipt = {
        "schema": PREVIEW_SCHEMA,
        "draft_sha256": digest,
        "effects": effects,
        "resolved_inputs": deepcopy(body.get("resolved_inputs", {})),
        "mutation_count": body.get("mutation_count"),
        "approval_status": "NOT_REQUESTED",
        "execution_allowed": False,
        "authority": "EXPLANATORY_PREVIEW_ONLY_NOT_SERVER_AUTHORIZATION",
    }
    receipt["preview_sha256"] = _digest(receipt)
    return receipt


def correct_workflow(specification: Mapping[str, Any],
                     corrections: Sequence[Mapping[str, Any]],
                     documents: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Apply narrowly scoped changes to the caller's specification and recompile.

    Never patches a previously approved draft: all corrections produce a new
    fingerprint, and any existing preview or approval MUST be invalidated.
    """
    if not isinstance(specification, Mapping):
        raise ValueError("specification must be an object")
    if not isinstance(corrections, list) or not 1 <= len(corrections) <= MAX_CORRECTIONS:
        raise ValueError("corrections must be a bounded list")
    updated = deepcopy(dict(specification))
    for correction in corrections:
        if not isinstance(correction, Mapping) or set(correction) != {"path", "value"}:
            raise ValueError("correction must contain only path and value")
        path = correction["path"]
        if not isinstance(path, list) or not 2 <= len(path) <= MAX_PATH_DEPTH:
            raise ValueError("correction path must be a bounded list")
        # Restrict correction to known user-editable fields of the original spec.
        if path[0] == "input_bindings":
            if len(path) != 2 or path[1] not in {"TARGET", "REFERENCE", "TEMPLATE"}:
                raise ValueError("unsupported input correction")
        elif path[0] == "steps":
            if len(path) < 4 or not isinstance(path[1], int) or isinstance(path[1], bool) or path[2] != "task":
                raise ValueError("unsupported task correction")
            if path[3] in {"task_sha256", "schema", "approval", "approved", "executable"}:
                raise ValueError("authority fields cannot be corrected")
        else:
            raise ValueError("unsupported correction root")
        node: Any = updated
        for part in path[:-1]:
            if isinstance(node, list):
                if not isinstance(part, int) or isinstance(part, bool) or part < 0 or part >= len(node):
                    raise ValueError("correction index out of range")
                node = node[part]
            elif isinstance(node, dict):
                if not isinstance(part, str) or part not in node:
                    raise ValueError("correction cannot create nested paths")
                node = node[part]
            else:
                raise ValueError("correction path is not traversable")
        last = path[-1]
        if not isinstance(node, dict) or not isinstance(last, str) or last not in node:
            raise ValueError("correction target must be an existing field")
        node[last] = deepcopy(correction["value"])
    result = compile_workflow(updated, documents)
    return {"specification": updated, "draft": result,
            "prior_approvals_valid": False, "execution_allowed": False,
            "authority": "CORRECTED_DRAFT_REQUIRES_NEW_SERVER_PREVIEW"}
