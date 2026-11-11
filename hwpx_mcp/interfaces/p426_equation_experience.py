"""Editable EqEdit equation diagnostics and owned-HWPX equation inspection.

P4.26 deliberately separates native EqEdit *script* evidence from a
renderer preview. No SVG/PNG/PDF is claimed by these methods.
"""
from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

from hwpx.equation import latex_to_eqedit
from hwpx.equation.authoring import UnsupportedLatexError
from hwpx_mcp.equations.p426_latex_compatibility import normalize_equation_latex


def describe_equation(latex: str, policy: str = "strict") -> dict:
    if not isinstance(latex, str) or not latex.strip() or len(latex) > 8192:
        raise ValueError("LATEX_EQUATION_INVALID")
    compatibility = normalize_equation_latex(latex, policy=policy)
    try:
        script = latex_to_eqedit(compatibility["normalized_latex"])
    except UnsupportedLatexError as exc:
        # Preserve the exact incompatibility, instead of substituting
        # printable text or an image and claiming it is editable math.
        raise ValueError(f"LATEX_TO_EQEDIT_UNSUPPORTED: {exc}") from exc
    if not isinstance(script, str) or not script.strip():
        raise ValueError("EQEDIT_COMPILATION_EMPTY")
    return {
        "input_latex": latex.strip(),
        "normalized_latex": compatibility["normalized_latex"],
        "compatibility": compatibility,
        "latex_sha256": hashlib.sha256(latex.strip().encode("utf-8")).hexdigest(),
        "eqedit_script": script,
        "eqedit_script_sha256": hashlib.sha256(script.encode("utf-8")).hexdigest(),
        "native_object_kind": "HWPX_OWPML_EQUATION",
        "editable_in_hancom": True,
        "native_render_verified": False,
        "rendering_authority": "SCRIPT_COMPILATION_ONLY",
    }


def register_equation_experience(core):
    @core.mcp.tool()
    def preview_native_equation_script(
        latex: str, policy: str = "strict",
    ) -> dict:
        """Convert LaTeX into actual HWP EqEdit script without inserting it."""
        core._caller_subject()
        return {"ok": True, **describe_equation(latex, policy=policy)}

    @core.mcp.tool()
    def inspect_document_equations(
        document_id: str, offset: int = 0, limit: int = 20,
        include_script: bool = True,
    ) -> dict:
        """Read native saved EqEdit equations with exact source/geometry data."""
        if type(offset) is not int or offset < 0:
            raise ValueError("OFFSET_INVALID")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("LIMIT_INVALID")
        subject = core._caller_subject()
        core._paths(document_id)
        row = core.DOCUMENT_STORE.load_current(document_id)
        if row is None or row.get("owner_subject") != subject:
            raise FileNotFoundError("OWNED_EQUATION_DOCUMENT_NOT_FOUND")
        from hwpx_mcp.document.p210_equations import build_equation_map
        with tempfile.TemporaryDirectory(prefix="p426-equation-read-") as tmp:
            source = Path(tmp) / "source.hwpx"
            source.write_bytes(row["bytes"])
            mapped = build_equation_map(source)
        data = mapped["equations"]
        return {
            "ok": True, "document_id": document_id,
            "revision": row["revision"],
            "equation_count": len(data),
            "equations": [
                {
                    "locator": item["locator"],
                    "section_index": item["section_index"],
                    "paragraph_locator": item["paragraph_locator"],
                    "script_sha256": item["script_sha256"],
                    "base_unit": item["base_unit"],
                    "width": item["width"], "height": item["height"],
                    **({"script": item["script"]} if include_script else {}),
                } for item in data[offset:offset + limit]
            ],
            "next_offset": offset + limit if offset + limit < len(data) else None,
            "equation_script_custody_sha256": mapped["equation_script_custody_sha256"],
            "native_render_verified": False,
        }
