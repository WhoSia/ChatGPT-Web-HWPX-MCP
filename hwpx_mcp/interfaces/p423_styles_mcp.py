"""Minimal authenticated MCP surface for opt-in reference style discovery.

Avoid a second server-side profile database. The caller receives a candidate
and explicitly supplies an approved profile to existing create_document_from_plan.
"""
from __future__ import annotations

from typing import Callable, Any

from mcp.types import ToolAnnotations

from hwpx_mcp.document.p423_reference_style import profile_from_reference


def register_p423_style_tools(
    core: Any,
    *,
    owned_document: Callable[[str], tuple[dict, Any]],
) -> None:
    read = ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        openWorldHint=False,
    )

    @core.mcp.tool(annotations=read)
    def get_p423_reference_style_candidate(
        document_id: str,
        profile_name: str = "reference-style",
        expected_revision: int | None = None,
    ) -> dict:
        """Extract a reviewable style candidate from an owned HWPX.

        Does not store a preference, change a document or grant permission to
        use the result in another document without the user's acceptance.
        """
        core._caller_subject()
        if not isinstance(document_id, str) or not document_id.strip():
            raise ValueError("document_id is required")
        metadata, path = owned_document(document_id)
        current = int(metadata["revision"])
        if expected_revision is not None:
            if type(expected_revision) is not int or expected_revision != current:
                raise ValueError("reference document revision mismatch")
        proposal = profile_from_reference(path, name=profile_name)
        return {
            "ok": True,
            "document_id": document_id,
            "reference_revision": current,
            "reference_sha256": metadata.get("sha256"),
            "candidate": proposal,
            "approval_required": True,
            "next_step": (
                "Review candidate.style_profile and warnings; explicitly pass "
                "an accepted profile via create_document_from_plan(plan.style_profile)."
            ),
            "stored_preference": False,
            "document_modified": False,
        }
