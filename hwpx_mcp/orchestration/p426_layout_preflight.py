"""Static layout-fit advice for a native HWPX authoring plan (not a renderer)."""
from __future__ import annotations

from typing import Any

from hwpx_mcp.orchestration.p426_layout_tokens import compile_layout_tokens

HWP_UNITS_PER_MM = 7200.0 / 25.4


def assess_native_layout(plan: dict[str, Any], layout: str | dict = "science-lab") -> dict:
    """Return grounded mechanical fit hints, not invented pixel placements."""
    if not isinstance(plan, dict):
        raise ValueError("LAYOUT_PLAN_INVALID")
    design = compile_layout_tokens(layout)
    content_mm = design["geometry"]["content_width_mm"]
    content_units = content_mm * HWP_UNITS_PER_MM
    blocks = plan.get("blocks")
    if not isinstance(blocks, list):
        sections = plan.get("sections", [])
        if not isinstance(sections, list):
            raise ValueError("LAYOUT_SECTIONS_INVALID")
        blocks = []
        for section in sections:
            if not isinstance(section, dict) or not isinstance(section.get("blocks", []), list):
                raise ValueError("LAYOUT_SECTION_BLOCKS_INVALID")
            blocks.extend(section.get("blocks", []))
    issues = []
    for index, block in enumerate(blocks):
        if not isinstance(block, dict):
            raise ValueError("LAYOUT_BLOCK_INVALID")
        kind = block.get("type")
        label = str(block.get("id", f"block-{index + 1}"))
        if kind in ("picture", "image", "table", "equation"):
            width = block.get("width")
            if width is None:
                if kind == "table" and block.get("cols", 0) > 10:
                    issues.append({
                        "block": label, "severity": "REVIEW",
                        "code": "MANY_TABLE_COLUMNS",
                        "message": "Review column widths and text wrapping in the native renderer.",
                    })
                continue
            if type(width) is not int or width <= 0:
                issues.append({
                    "block": label, "severity": "INVALID",
                    "code": "NATIVE_WIDTH_INVALID",
                    "message": "Native object width must be a positive integer.",
                })
                continue
            if width > content_units:
                issues.append({
                    "block": label, "severity": "REVIEW",
                    "code": "OBJECT_EXCEEDS_BODY_WIDTH",
                    "native_width": width,
                    "body_width_native_approx": round(content_units),
                    "message": "Object width exceeds the approximate available content width.",
                })
    return {
        "status": "INVALID" if any(i["severity"] == "INVALID" for i in issues)
            else ("REVIEW" if issues else "NO_STATIC_WIDTH_FLAGS"),
        "design_sha256": design["tokens_sha256"],
        "content_width_mm": content_mm,
        "content_height_mm": design["geometry"]["content_height_mm"],
        "native_units_per_mm_assumption": HWP_UNITS_PER_MM,
        "issues": issues,
        "authority": "STATIC_PREVIEW_ONLY_NOT_HANCOM_RENDER",
    }
