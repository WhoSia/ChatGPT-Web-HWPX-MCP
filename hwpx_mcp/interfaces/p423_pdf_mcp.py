"""Owner-checked native PDF conversion tool for a licensed Windows Hwp.exe host.

On Linux (including Render) this MUST return unavailable, not a substitute
PDF from a different layout engine. For small native PDFs a bounded base64
payload is a temporary delivery mechanism pending immutable PDF custody.
"""
from __future__ import annotations

import base64
import hashlib
from pathlib import Path
import tempfile
from typing import Any, Callable

from mcp.types import ToolAnnotations

from hwpx_mcp.custody.p423_hancom_pdf import (
    export_native_hwp_pdf, native_pdf_capability, HancomPdfUnavailable,
)

MAX_INLINE_PDF_BYTES = 4 * 1024 * 1024


def register_p423_native_pdf_tools(
    core: Any,
    *,
    owned_document: Callable[[str], tuple[dict, Path]],
) -> None:
    read = ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, openWorldHint=False
    )

    @core.mcp.tool(annotations=read)
    def get_p423_native_pdf_capability() -> dict:
        """Discover whether this MCP host has native Windows Hangul PDF export."""
        core._caller_subject()
        return {"ok": True, **native_pdf_capability(), "max_inline_pdf_bytes": MAX_INLINE_PDF_BYTES}

    @core.mcp.tool(annotations=read)
    def export_p423_owned_hwp_as_native_pdf(
        document_id: str,
        expected_revision: int,
    ) -> dict:
        """Convert an owner-verified HWPX using Hwp.exe SaveAs('PDF').

        The PDF is native-rendered but has not passed page-by-page human
        visual acceptance. In a Linux deployment it is unavailable.
        """
        core._caller_subject()
        if not isinstance(document_id, str) or not document_id.strip():
            raise ValueError("document_id is required")
        if type(expected_revision) is not int or expected_revision <= 0:
            raise ValueError("expected_revision must be a positive integer")
        metadata, source = owned_document(document_id)
        if int(metadata["revision"]) != expected_revision:
            raise ValueError("document revision changed; refresh before export")
        capability = native_pdf_capability()
        if not capability["available"]:
            return {
                "ok": False,
                "code": "WINDOWS_HANCOM_AGENT_REQUIRED",
                "native_pdf_created": False,
                "required_engine": "HANCOM_HWP_EXE_COM",
                "source_revision": expected_revision,
                "next": "Run this export on a licensed Windows Hancom worker",
            }
        with tempfile.TemporaryDirectory(prefix="p423-native-") as temp:
            destination = Path(temp) / "native.pdf"
            receipt = export_native_hwp_pdf(source, destination)
            content = destination.read_bytes()
            pdf_sha = hashlib.sha256(content).hexdigest()
            if receipt.get("pdf_sha256") != pdf_sha or not content.startswith(b"%PDF-"):
                raise ValueError("native PDF output does not match worker receipt")
            # A long-running Hancom conversion must not publish an obsolete
            # revision after another caller edits the owned document.
            current_metadata, _ = owned_document(document_id)
            if int(current_metadata["revision"]) != expected_revision:
                raise ValueError("document revision changed during native export")
            if len(content) > MAX_INLINE_PDF_BYTES:
                return {
                    "ok": False,
                    "code": "PDF_TOO_LARGE_FOR_INLINE_DELIVERY",
                    "native_pdf_created": True,
                    "pdf_bytes": len(content),
                    "pdf_sha256": receipt["pdf_sha256"],
                    "next": "Requires authenticated binary PDF storage and signed delivery",
                }
            return {
                "ok": True,
                "document_id": document_id,
                "source_revision": expected_revision,
                "native_pdf_created": True,
                "engine": "HANCOM_HWP_EXE_COM",
                "pdf_sha256": pdf_sha,
                "pdf_bytes": len(content),
                "pdf_base64": base64.b64encode(content).decode("ascii"),
                "mime_type": "application/pdf",
                "native_visual_acceptance": "NOT_ADJUDICATED",
                "receipt": receipt,
            }
