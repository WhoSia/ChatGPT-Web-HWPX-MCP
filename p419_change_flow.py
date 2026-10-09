"""P4.19 one-step end-user edit staging: user intent -> human review.

The ChatGPT client interprets the natural-language title request into typed fields.
This service does not pretend to contain a free-form LLM or execute edits itself.
"""
from __future__ import annotations

import os
import time

from hwpx_mcp.orchestration.p418_p2_workflow import compile_workflow
from hwpx_mcp.orchestration.p418_p2_preview import preview_workflow

SCHEMA = "chatgpt-web-hwpx-mcp/p4.19/title-change-stage/v1"


def stage_title_change(
    core, *, document_id: str, expected_revision: int, new_title: str,
    stage_adapter, now: float | None = None,
) -> dict:
    """One owner-scoped request replaces three fragile manually composed calls.

    This only persists an UNAPPROVED review. The independent browser is the
    exclusive approval/mutation boundary. All server-custody and CAS checks
    are delegated to the existing P4.18 staging adapter.
    """
    if not isinstance(document_id, str) or not document_id:
        raise ValueError("document_id must be provided")
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 1:
        raise ValueError("expected_revision must be a positive integer")
    if (not isinstance(new_title, str) or not new_title.strip() or
        len(new_title) > 500 or any(ord(c) < 32 for c in new_title)):
        raise ValueError("new_title must be one nonempty line of at most 500 characters")

    # Do not allocate a staged workflow which cannot be approved.
    base_url = str(getattr(core, "PUBLIC_BASE_URL", ""))
    if (not base_url.startswith("https://") or
        len(os.environ.get("P418_HOST_REVIEW_PASSPHRASE", "")) < 24 or
        len(os.environ.get("P418_HOST_APPROVAL_SIGNING_SECRET", "")) < 32):
        raise RuntimeError("Independent browser approval host is unavailable")

    # _require_owner uses authenticated MCP subject, never a caller-owned name.
    metadata = core._load_metadata(document_id)
    core._require_owner(metadata)
    revision = int(metadata["revision"])
    if expected_revision != revision:
        raise ValueError("Document revision changed; inspect the current version")
    remaining = float(metadata["expires_at_epoch"]) - (
        time.time() if now is None else now
    )
    if remaining < 900:
        raise ValueError("Document expires too soon for safe human review")

    task = {
        "kind": "EDIT_INTENT", "document_id": document_id,
        "expected_revision": revision,
        "intent": {"actions": [
            {"action": "replace_role_text", "role": "TITLE", "text": new_title}
        ]},
    }
    specification = {
        "steps": [{"task": task}],
        "input_bindings": {"TARGET": document_id},
    }
    draft = compile_workflow(
        specification, [{"document_id": document_id, "revision": revision}]
    )
    if draft["mutation_count"] != 1 or draft["executable"]:
        raise RuntimeError("Unexpected workflow effects")
    preview = preview_workflow(draft)
    if preview.get("execution_allowed", False):
        raise RuntimeError("Preview cannot authorize execution")
    staged = stage_adapter(draft, preview)
    if not staged.get("ok") or staged.get("state") != "STAGED" or not staged.get("human_review_url"):
        raise RuntimeError("Human approval stage was not available")
    return {
        "ok": True, "schema": SCHEMA,
        "document_id": document_id, "expected_revision": revision,
        "source_sha256": metadata["sha256"],
        "change": {"action": "replace_role_text", "role": "TITLE", "text": new_title},
        "draft_sha256": draft["draft_sha256"],
        "preview_sha256": preview["preview_sha256"],
        "workflow_id": staged["workflow_id"],
        "expires_at": staged["expires_at"],
        "human_review_url": staged["human_review_url"],
        "state": "STAGED", "approval_granted": False,
        "mutation_executed": False,
        "authority": "SERVER_VERIFIED_STAGING_ONLY_INDEPENDENT_HUMAN_APPROVAL_REQUIRED",
    }
