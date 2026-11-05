"""Minimal authenticated MCP surface for opt-in reference style discovery.

Avoid a second server-side profile database. The caller receives a candidate
and explicitly supplies an approved profile to existing create_document_from_plan.
"""
from __future__ import annotations

import hmac
import re
from typing import Callable, Any

from mcp.types import ToolAnnotations

from hwpx_mcp.document.p423_reference_style import profile_from_reference


def register_p423_style_tools(
    core: Any,
    *,
    owned_document: Callable[[str], tuple[dict, Any]],
    create_adapter: Callable[..., Any] | None = None,
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

    if create_adapter is not None:
        write = ToolAnnotations(
            readOnlyHint=False, destructiveHint=False, openWorldHint=False,
        )

        @core.mcp.tool(annotations=write)
        def create_p423_document_with_approved_reference_style(
            reference_document_id: str,
            expected_reference_revision: int,
            accepted_profile_sha256: str,
            plan: dict,
            profile_name: str = "reference-style",
            filename: str = "document.hwpx",
            template_document_id: str = "",
            request_id: str = "",
        ) -> dict:
            """Generate with an explicitly approved, revision-pinned reference style.

            This uses the existing validated atomic document composer. Merely
            providing a reference ID does not count as approval.
            """
            core._caller_subject()
            if not isinstance(reference_document_id, str) or not reference_document_id.strip():
                raise ValueError("reference_document_id is required")
            if type(expected_reference_revision) is not int:
                raise ValueError("expected_reference_revision must be an integer")
            if not isinstance(accepted_profile_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", accepted_profile_sha256) is None:
                raise ValueError("accepted_profile_sha256 must be 64 lowercase hex characters")
            if not isinstance(plan, dict) or "style_profile" in plan:
                raise ValueError("plan must be an object without an implicit style_profile")
            metadata, path = owned_document(reference_document_id)
            if int(metadata["revision"]) != expected_reference_revision:
                raise ValueError("reference document revision mismatch")
            proposal = profile_from_reference(path, name=profile_name)
            fingerprint = proposal["style_profile_sha256"]
            if not hmac.compare_digest(fingerprint, accepted_profile_sha256):
                raise ValueError("reference style has changed or was not approved")
            approved_plan = dict(plan)
            approved_plan["style_profile"] = proposal["style_profile"]
            result = create_adapter(
                approved_plan,
                filename=filename,
                template_document_id=template_document_id,
                request_id=request_id,
            )
            if not isinstance(result, dict):
                raise TypeError("create adapter must return a document receipt")
            return {
                **result,
                "reference_style": {
                    "source_document_id": reference_document_id,
                    "source_revision": int(metadata["revision"]),
                    "approved_profile_sha256": fingerprint,
                    "source_sha256": metadata.get("sha256"),
                    "warnings": proposal.get("warnings", []),
                    "user_approval_required_before_call": True,
                },
            }
