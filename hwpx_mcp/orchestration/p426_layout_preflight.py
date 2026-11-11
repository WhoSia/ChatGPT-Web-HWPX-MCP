"""Static layout-fit advice for a native HWPX authoring plan (not a renderer)."""
from __future__ import annotations

from typing import Any
from copy import deepcopy

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
        if kind == "table":
            policy = block.get("table_format") or {}
            if not isinstance(policy, dict):
                raise ValueError("LAYOUT_TABLE_FORMAT_INVALID")
            mode = str(policy.get("page_break", design["tokens"]["table"]["page_break"])).upper()
            rows = block.get("rows", 0)
            cols = block.get("cols", 0)
            if type(rows) is not int or type(cols) is not int or rows < 0 or cols < 0:
                raise ValueError("LAYOUT_TABLE_DIMENSIONS_INVALID")
            if rows >= 40 and mode in ("TABLE", "NONE"):
                issues.append({
                    "block": label, "severity": "REVIEW",
                    "code": "LONG_TABLE_WITHOUT_CELL_SPLIT",
                    "rows": rows, "page_break": mode,
                    "message": "A long table uses a non-cell page break mode; verify its native pagination.",
                })
            repeat = policy.get("repeat_header", design["tokens"]["table"]["repeat_header"])
            header = policy.get("first_row_header", block.get("first_row_header", False))
            if rows >= 40 and not (repeat and header):
                issues.append({
                    "block": label, "severity": "REVIEW",
                    "code": "LONG_TABLE_WITHOUT_REPEATED_HEADER",
                    "rows": rows,
                    "message": "Long native tables benefit from a marked, repeating first header row.",
                })
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

def fit_native_pictures_to_body(
    blocks: list[dict], layout: str | dict = "science-lab",
    *, inset_mm: float = 2.0,
) -> dict:
    """Opt-in, aspect-preserving resize of pictures wider than A4 text area.

    Native HWPUNIT dimensions are updated in the plan; image bytes are never
    resized, re-encoded, cropped or deleted. Other block types stay unchanged.
    """
    if not isinstance(blocks, list):
        raise ValueError("LAYOUT_PICTURE_BLOCKS_INVALID")
    if type(inset_mm) not in (int, float) or not 0 <= inset_mm <= 20:
        raise ValueError("LAYOUT_INSET_INVALID")
    design = compile_layout_tokens(layout)
    content_mm = design["geometry"]["content_width_mm"]
    limit = int((content_mm - 2 * inset_mm) * HWP_UNITS_PER_MM)
    if limit <= 0:
        raise ValueError("LAYOUT_AVAILABLE_WIDTH_INVALID")
    result = deepcopy(blocks)
    adjustments = []
    for index, block in enumerate(result):
        if not isinstance(block, dict):
            raise ValueError("LAYOUT_BLOCK_INVALID")
        if block.get("type") not in ("picture", "image"):
            continue
        width, height = block.get("width", 10000), block.get("height", 8000)
        if (type(width) is not int or type(height) is not int
                or width <= 0 or height <= 0):
            raise ValueError("LAYOUT_PICTURE_DIMENSIONS_INVALID")
        if width <= limit:
            continue
        scale = limit / width
        new_height = max(1, round(height * scale))
        block["width"] = limit
        block["height"] = new_height
        adjustments.append({
            "index": index, "block_id": block.get("id"),
            "previous_width": width, "previous_height": height,
            "new_width": limit, "new_height": new_height,
            "scale": scale,
        })
    return {
        "blocks": result, "adjustments": adjustments,
        "adjusted_count": len(adjustments),
        "content_width_mm": content_mm,
        "inset_mm": inset_mm,
        "pixel_data_resampled": False,
        "authority": "NATIVE_PLAN_GEOMETRY_ONLY",
    }
