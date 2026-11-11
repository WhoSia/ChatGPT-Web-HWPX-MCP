"""P4.26 optional SVG preview served from an owned retained HWPX revision.

This is not a native Hancom fidelity assertion. A rhwp executable must
be installed in the server runtime for actual rendered SVG output.
"""
from __future__ import annotations

import base64
import tempfile
from pathlib import Path

from hwpx_mcp.render.p426_rhwp_svg_preview import (
    RhwpPreviewUnavailable, render_svg_manifest, rhwp_capability,
)
from hwpx_mcp.custody.p423_hancom_pdf import native_pdf_capability

MAX_PAGE_SVG_BYTES = 512_000
MAX_INLINE_SVG_PAGES = 3


def register_visual_preview(core):
    @core.mcp.tool()
    def get_document_render_options() -> dict:
        """Discover real renderer capabilities, not a simulated page preview."""
        core._caller_subject()
        return {
            "ok": True,
            "svg_preview": rhwp_capability(),
            "native_hancom_pdf": native_pdf_capability(),
            "preferred_fidelity_reference": "HANCOM_HWP_EXE_COM",
            "preview_fidelity": "RHWP_ALTERNATIVE_RENDERER",
            "native_pdf_worker_hosted": False,
            "no_renderer_fallback": "STATIC_LAYOUT_DIAGNOSTICS_ONLY",
        }

    @core.mcp.tool()
    def preview_document_svg_pages(
        document_id: str,
        max_pages: int = 1,
        start_page: int = 0,
        profile: str = "screen",
    ) -> dict:
        """Render and return up to three SVG pages, only if rhwp is installed."""
        if type(max_pages) is not int or not 1 <= max_pages <= MAX_INLINE_SVG_PAGES:
            raise ValueError("PREVIEW_PAGE_LIMIT_INVALID")
        if type(start_page) is not int or start_page < 0:
            raise ValueError("PREVIEW_START_PAGE_INVALID")
        owner = core._caller_subject()
        core._paths(document_id)
        row = core.DOCUMENT_STORE.load_current(document_id)
        if row is None or row.get("owner_subject") != owner:
            raise FileNotFoundError("OWNED_DOCUMENT_NOT_AVAILABLE")
        if not rhwp_capability()["available"]:
            return {
                "ok": False, "status": "RENDERER_NOT_INSTALLED",
                "native_pdf_created": False,
                "fallback": "Use P4.26 report layout diagnostics.",
            }
        with tempfile.TemporaryDirectory(prefix="p426-rhwp-pages-") as tmp:
            root = Path(tmp)
            source = root / "owned.hwpx"
            source.write_bytes(row["bytes"])
            pages = []
            incomplete_reason = None
            for page_index in range(start_page, start_page + max_pages):
                out = root / f"page-{page_index}"
                out.mkdir()
                try:
                    render = render_svg_manifest(
                        source, out, profile=profile,
                        max_pages=1, page_index=page_index,
                    )
                except RhwpPreviewUnavailable as exc:
                    incomplete_reason = str(exc)
                    break
                if len(render["pages"]) != 1:
                    incomplete_reason = "RHWP_SINGLE_PAGE_MANIFEST_INVALID"
                    break
                item = render["pages"][0]
                data = Path(item["path"]).read_bytes()
                if len(data) > MAX_PAGE_SVG_BYTES:
                    incomplete_reason = "SVG_PAGE_TOO_LARGE"
                    break
                pages.append({
                    "page": item["page"],
                    "svg_base64": base64.b64encode(data).decode("ascii"),
                    "sha256": item["sha256"], "bytes": item["bytes"],
                    "mime_type": "image/svg+xml",
                    "overflow_cell_lines": item["overflow_cell_lines"],
                })
            if not pages:
                return {"ok": False,
                        "status": incomplete_reason or "RHWP_NO_PAGES_RENDERED",
                        "native_pdf_created": False}
        return {
            "ok": True, "document_id": document_id, "revision": row["revision"],
            "status": "SVG_PAGES_READY", "pages": pages,
            "partial": incomplete_reason is not None,
            "incomplete_reason": incomplete_reason,
            "next_page": start_page + len(pages),
            "render_authority": "THIRD_PARTY_SVG_NOT_NATIVE_HANCOM",
            "native_pdf_created": False,
            "client_visual_display_verified": False,
        }
