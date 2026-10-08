"""P4.18-P3 full-fidelity human review packet, not approval authority.

A trusted interactive host must load the server-staged inputs, authenticate
the viewer, HTML-escape every displayed data field, capture actual human
intent, and independently sign the consent envelope. Merely producing this
packet neither proves custody nor grants authorization.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import json
import re
from typing import Any

from hwpx_mcp.orchestration.p418_p2_admission import AdmissionError, canonical_sha
from hwpx_mcp.orchestration.p418_p2_preview import preview_workflow
from p418_product import normalize_document_task

MAX_REVIEW_BYTES = 131072
_SHA = re.compile(r"^[0-9a-f]{64}$")


def prepare_native_edit_review_packet(
    *, owner: str, workflow_id: str, ledger: Any,
    draft: Mapping[str, Any], preview: Mapping[str, Any],
    staged_bindings: Mapping[str, Any],
) -> dict[str, Any]:
    """Preserve *all* user-visible effects and full normalized task payload."""
    if not isinstance(owner, str) or not owner.strip():
        raise AdmissionError("authenticated host review owner required")
    if not isinstance(workflow_id, str) or not workflow_id or not callable(getattr(ledger, "get_staged_review_identity", None)):
        raise AdmissionError("server-owned staged review ledger and workflow required")
    try:
        canonical = preview_workflow(draft)
        if not isinstance(preview, Mapping) or canonical != dict(preview):
            raise AdmissionError("review preview differs from canonical draft")
        steps = draft["steps"]
        if not isinstance(steps, list) or len(steps) != 1:
            raise AdmissionError("host edit review must contain exactly one step")
        step = steps[0]
        task = step["task"]
        if step.get("effect") != "MUTATION" or task.get("kind") != "EDIT_INTENT":
            raise AdmissionError("native edit review requires one EDIT_INTENT")
        if normalize_document_task(task) != task:
            raise AdmissionError("review contains a noncanonical task")
        if not isinstance(staged_bindings, Mapping) or set(staged_bindings) != {"documents"}:
            raise AdmissionError("host must supply staged document snapshot")
        rows = staged_bindings["documents"]
        if not isinstance(rows, list):
            raise AdmissionError("staged document list required")
        expected = [("document_id", task["document_id"])]
        if task["reference_document_id"]:
            expected.append(("reference_document_id", task["reference_document_id"]))
        if len(rows) != len(expected):
            raise AdmissionError("staged and reviewed document count differs")
        for row, (role, target_id) in zip(rows, expected):
            if not isinstance(row, Mapping) or row.get("role") != role or row.get("document_id") != target_id:
                raise AdmissionError("staged and reviewed document identity differs")
            if type(row.get("revision")) is not int or row["revision"] < 1:
                raise AdmissionError("review revision must be a positive integer")
            if not isinstance(row.get("sha256"), str) or not _SHA.fullmatch(row["sha256"]):
                raise AdmissionError("review requires committed source SHA-256")
        if rows[0]["revision"] != task["expected_revision"]:
            raise AdmissionError("review source revision differs from task")
        staged_identity = ledger.get_staged_review_identity(owner=owner, workflow_id=workflow_id)
        expected_identity = {
            "draft_sha256": draft["draft_sha256"],
            "preview_sha256": canonical["preview_sha256"],
            "binding_sha256": canonical_sha(staged_bindings),
            "effect_scope": "EDIT_INTENT",
        }
        if staged_identity != expected_identity:
            raise AdmissionError("review does not match server-owned staged identity")
        packet = {
            "schema": "chatgpt-web-hwpx-mcp/p4.18-p3/native-edit-review/v1",
            "workflow_id": workflow_id,
            "owner": owner,
            "draft_sha256": draft["draft_sha256"],
            "preview_sha256": canonical["preview_sha256"],
            "staged_binding_sha256": canonical_sha(staged_bindings),
            "effect_scope": "EDIT_INTENT",
            "source": {
                "document_id": rows[0]["document_id"],
                "expected_revision": rows[0]["revision"],
                "source_sha256": rows[0]["sha256"],
            },
            "references": deepcopy([dict(row) for row in rows[1:]]),
            # Do not show only a summary: the host must display these complete
            # normalized effects before any human confirmation is accepted.
            "complete_task": deepcopy(dict(task)),
            "requested_actions": deepcopy(task["intent"].get("actions", [])),
            "preservation": deepcopy(task["intent"].get("preservation", {})),
            "decision": "AWAITING_INDEPENDENT_HUMAN_CONFIRMATION",
            "approval_granted": False,
            "execution_allowed": False,
            "authority": "HOST_REVIEW_INPUT_ONLY_NO_AUTHORIZATION",
        }
        if len(json.dumps(packet, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_REVIEW_BYTES:
            raise AdmissionError("review payload too large for complete human review")
        packet["review_packet_sha256"] = canonical_sha(packet)
        return packet
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, AdmissionError):
            raise
        raise AdmissionError("invalid canonical native edit review input") from exc
