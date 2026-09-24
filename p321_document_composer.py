from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable

from hwpx import HwpxDocument
from hwpx.equation import latex_to_eqedit

from p2_document import build_document_map
from p22_formatting import build_formatting_map
from p23_richtext import apply_rich_formatting_atomic
from p27_tables import _save_document
from p28_tables import build_table_map
from p323_advanced_tables import build_advanced_table_map, apply_advanced_table_edits_atomic
from p29_objects import build_object_map
from p210_equations import build_equation_map
from p318_document_setup import apply_document_setup_atomic, build_document_setup_map
from p319_structured_publishing import (
    apply_structured_publishing_atomic,
    build_structured_publishing_map,
)
from p320_annotation_apparatus import (
    apply_annotation_apparatus_atomic,
    build_annotation_apparatus_map,
)


PLAN_SCHEMA = "chatgpt-web-hwpx-mcp/document-plan/p3.21/v1"
RECEIPT_SCHEMA = "chatgpt-web-hwpx-mcp/document-composition-receipt/p3.21/v1"
MAX_BLOCKS = 240
MAX_IMAGE_BYTES = 8 * 1024 * 1024

PRESETS: dict[str, dict[str, Any]] = {
    "default": {
        "setup": [],
        "title_format": {},
        "body_format": {},
    },
    "school-report": {
        "setup": [{
            "op": "set_page_setup",
            "section_index": 0,
            "paper_size": "A4",
            "orientation": "PORTRAIT",
            "margin_left_mm": 20,
            "margin_right_mm": 20,
            "margin_top_mm": 18,
            "margin_bottom_mm": 18,
        }],
        "title_format": {
            "run": {"bold": True, "size": 20},
            "paragraph": {"alignment": "CENTER", "spacing_after_pt": 14},
        },
        "body_format": {
            "paragraph": {"line_spacing_percent": 160},
        },
    },
    "academic-report": {
        "setup": [{
            "op": "set_page_setup",
            "section_index": 0,
            "paper_size": "A4",
            "orientation": "PORTRAIT",
            "margin_left_mm": 25,
            "margin_right_mm": 25,
            "margin_top_mm": 20,
            "margin_bottom_mm": 20,
        }],
        "title_format": {
            "run": {"bold": True, "size": 18},
            "paragraph": {"alignment": "CENTER", "spacing_after_pt": 12},
        },
        "body_format": {
            "paragraph": {"line_spacing_percent": 150},
        },
    },
    "institutional-report": {
        "setup": [{
            "op": "set_page_setup",
            "section_index": 0,
            "paper_size": "A4",
            "orientation": "PORTRAIT",
            "margin_left_mm": 20,
            "margin_right_mm": 20,
            "margin_top_mm": 18,
            "margin_bottom_mm": 18,
        }],
        "title_format": {
            "run": {"bold": True, "size": 18, "font_by_script": {"hangul": "함초롬바탕", "latin": "Malgun Gothic"}},
            "paragraph": {"alignment": "CENTER", "spacing_after_pt": 12, "keep_with_next": True},
        },
        "heading_format": {
            "1": {"run": {"bold": True, "size": 14}, "paragraph": {"spacing_before_pt": 12, "spacing_after_pt": 6, "keep_with_next": True}},
            "2": {"run": {"bold": True, "size": 12}, "paragraph": {"spacing_before_pt": 9, "spacing_after_pt": 4, "keep_with_next": True}},
        },
        "body_format": {
            "run": {"size": 11, "font_by_script": {"hangul": "함초롬바탕", "latin": "Malgun Gothic"}},
            "paragraph": {"line_spacing_percent": 160},
        },
        "table_format": {"page_break": "CELL", "border_color": "808080"},
    },
    "polished-report": {
        "setup": [{
            "op": "set_page_setup",
            "section_index": 0,
            "paper_size": "A4",
            "orientation": "PORTRAIT",
            "margin_left_mm": 22,
            "margin_right_mm": 22,
            "margin_top_mm": 20,
            "margin_bottom_mm": 20,
        }],
        "title_format": {
            "run": {"bold": True, "size": 22, "letter_spacing": -2, "font_by_script": {"hangul": "맑은 고딕", "latin": "Malgun Gothic"}},
            "paragraph": {"alignment": "CENTER", "spacing_after_pt": 18, "keep_with_next": True},
        },
        "heading_format": {
            "1": {"run": {"bold": True, "size": 15, "font_by_script": {"hangul": "맑은 고딕", "latin": "Malgun Gothic"}}, "paragraph": {"spacing_before_pt": 14, "spacing_after_pt": 7, "keep_with_next": True}},
            "2": {"run": {"bold": True, "size": 13, "font_by_script": {"hangul": "맑은 고딕", "latin": "Malgun Gothic"}}, "paragraph": {"spacing_before_pt": 10, "spacing_after_pt": 5, "keep_with_next": True}},
            "3": {"run": {"bold": True, "size": 11, "font_by_script": {"hangul": "맑은 고딕", "latin": "Malgun Gothic"}}, "paragraph": {"spacing_before_pt": 8, "spacing_after_pt": 4, "keep_with_next": True}},
        },
        "body_format": {
            "run": {"size": 11, "font_by_script": {"hangul": "맑은 고딕", "latin": "Malgun Gothic"}},
            "paragraph": {"line_spacing_percent": 155, "spacing_after_pt": 3},
        },
        "table_format": {"page_break": "CELL", "border_color": "AEB7C2"},
    },
}


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def document_plan_contract() -> dict:
    return {
        "schema": PLAN_SCHEMA,
        "presets": sorted(PRESETS),
        "block_types": [
            "title", "paragraph", "heading", "list_item", "table",
            "equation", "picture", "page_break", "section_break",
        ],
        "reference_syntax": {
            "block_id": "Each block may declare a unique id. Later operations can use $block:<id>.",
            "paragraph_fields": ["paragraph", "target_paragraph"],
        },
        "top_level": {
            "preset": "one of the advertised presets; P3.36 adds institutional-report and polished-report",
            "document": {"title": "optional logical title"},
            "setup": "optional document-setup operations",
            "blocks": "ordered block list",
            "publishing": {
                "toc": "bool or object",
                "page_numbers": "bool or object",
                "header": "optional string",
                "footer": "optional string",
            },
            "annotations": "optional annotation-apparatus operations using $block:<id>",
            "post_operations": "optional structured-publishing operations using $block:<id>",
            "table_design_fields": {
                "first_row_header": "bool; explicit semantic hint for repeat-header finishing",
                "table_format": "optional page_break, border_color, repeat_header overrides",
            },
        },
        "atomicity": (
            "The compiler builds and validates a private candidate package. "
            "The destination is replaced only after all stages succeed."
        ),
    }


def _normalize_plan(plan: dict) -> dict:
    if not isinstance(plan, dict):
        raise ValueError("plan must be an object")
    encoded_plan = json.dumps(plan, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded_plan) > 16 * 1024 * 1024:
        raise ValueError("document plan exceeds 16 MiB")
    preset = str(plan.get("preset", "default"))
    if preset not in PRESETS:
        raise ValueError(f"unknown document preset: {preset}")
    blocks = plan.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        raise ValueError("plan.blocks must be a non-empty list")
    if len(blocks) > MAX_BLOCKS:
        raise ValueError(f"plan exceeds {MAX_BLOCKS} blocks")

    normalized_blocks = []
    used_ids: set[str] = set()
    for index, raw in enumerate(blocks):
        if not isinstance(raw, dict):
            raise ValueError("each plan block must be an object")
        kind = str(raw.get("type") or "").strip()
        if kind not in {
            "title", "paragraph", "heading", "list_item", "table",
            "equation", "picture", "page_break", "section_break",
        }:
            raise ValueError(f"unsupported plan block type: {kind}")
        block_id = str(raw.get("id") or f"b{index + 1}").strip()
        if not block_id or len(block_id) > 100:
            raise ValueError("block id must be 1..100 characters")
        if block_id in used_ids:
            raise ValueError(f"duplicate block id: {block_id}")
        used_ids.add(block_id)
        item = dict(raw)
        item["id"] = block_id
        item["type"] = kind
        normalized_blocks.append(item)

    result = dict(plan)
    result["preset"] = preset
    result["blocks"] = normalized_blocks
    if "setup" in result and not isinstance(result["setup"], list):
        raise ValueError("plan.setup must be a list")
    if "annotations" in result and not isinstance(result["annotations"], list):
        raise ValueError("plan.annotations must be a list")
    if "post_operations" in result and not isinstance(result["post_operations"], list):
        raise ValueError("plan.post_operations must be a list")
    publishing = result.get("publishing", {})
    if publishing is not None and not isinstance(publishing, dict):
        raise ValueError("plan.publishing must be an object")
    return result


def validate_document_plan(plan: dict) -> dict:
    normalized = _normalize_plan(plan)
    counts: dict[str, int] = {}
    for block in normalized["blocks"]:
        counts[block["type"]] = counts.get(block["type"], 0) + 1
    return {
        "ok": True,
        "schema": PLAN_SCHEMA,
        "plan_sha256": _sha(normalized),
        "block_count": len(normalized["blocks"]),
        "block_counts": counts,
        "preset": normalized["preset"],
        "template_compatible": True,
    }


def _image_bytes(block: dict) -> tuple[bytes, str]:
    encoded = block.get("content_base64")
    if not isinstance(encoded, str) or not encoded:
        raise ValueError("picture block requires content_base64")
    if len(encoded) > ((MAX_IMAGE_BYTES + 2) // 3) * 4 + 16:
        raise ValueError("picture payload exceeds composition limit")
    try:
        payload = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("picture content_base64 is invalid") from exc
    if not payload or len(payload) > MAX_IMAGE_BYTES:
        raise ValueError("picture payload exceeds composition limit")
    fmt = str(block.get("image_format", "png")).lower().strip(".")
    if fmt not in {"png", "jpg", "jpeg", "gif", "bmp"}:
        raise ValueError("unsupported picture image_format")
    return payload, fmt


def _paragraph_id(paragraph: Any) -> str:
    value = paragraph.element.get("id")
    if not value:
        raise ValueError("composed paragraph has no intrinsic id")
    return str(value)


def _add_caption(obj: Any, block: dict) -> None:
    caption = block.get("caption")
    if caption is None:
        return
    text = str(caption)
    if not text:
        return
    side = str(block.get("caption_side", "BOTTOM")).upper()
    obj.set_caption(text, side=side)


def _materialize_blocks(document: HwpxDocument, blocks: list[dict]) -> dict[str, dict]:
    bindings: dict[str, dict] = {}
    list_groups: dict[tuple[str, int, str], list[str]] = {}
    table_index = 0

    for block in blocks:
        kind = block["type"]
        block_id = block["id"]

        if kind in {"title", "paragraph", "list_item"}:
            text = str(block.get("text") or "")
            paragraph = document.add_paragraph(text)
            pid = _paragraph_id(paragraph)
            bindings[block_id] = {"kind": kind, "paragraph_id": pid}
            if kind == "list_item":
                list_kind = str(block.get("kind", "bullet")).lower()
                level = int(block.get("level", 1))
                list_id = str(block.get("list_id", "default"))
                list_groups.setdefault((list_kind, level, list_id), []).append(block_id)
            continue

        if kind == "heading":
            text = str(block.get("text") or "")
            if not text:
                raise ValueError("heading block requires text")
            level = int(block.get("level", 1))
            if level < 1 or level > 10:
                raise ValueError("heading level must be 1..10")
            paragraph = document.add_heading(text, level=level)
            bindings[block_id] = {
                "kind": kind,
                "paragraph_id": _paragraph_id(paragraph),
                "level": level,
            }
            continue

        if kind == "table":
            rows = int(block.get("rows", 0))
            cols = int(block.get("cols", 0))
            if not 1 <= rows <= 200 or not 1 <= cols <= 100:
                raise ValueError("table rows/cols are outside admitted bounds")
            anchor = document.add_paragraph("")
            kwargs: dict[str, Any] = {}
            if block.get("width") is not None:
                kwargs["width"] = int(block["width"])
            if block.get("height") is not None:
                kwargs["height"] = int(block["height"])
            table = anchor.add_table(rows, cols, **kwargs)
            cells = block.get("cells")
            if cells is not None:
                if not isinstance(cells, list):
                    raise ValueError("table.cells must be a row list")
                for r, row in enumerate(cells[:rows]):
                    if not isinstance(row, list):
                        raise ValueError("table.cells rows must be lists")
                    for col, value in enumerate(row[:cols]):
                        table.cell(r, col).set_text(str(value))
            _add_caption(table, block)
            bindings[block_id] = {
                "kind": kind,
                "paragraph_id": _paragraph_id(anchor),
                "table_index": table_index,
            }
            table_index += 1
            continue

        if kind == "equation":
            latex = str(block.get("latex") or "").strip()
            if not latex:
                raise ValueError("equation block requires latex")
            script = latex_to_eqedit(latex)
            anchor = document.add_paragraph("")
            base_unit = int(block.get("base_unit", 1100))
            size = None
            if block.get("width") is not None or block.get("height") is not None:
                if block.get("width") is None or block.get("height") is None:
                    raise ValueError("equation explicit size requires width and height")
                size = (int(block["width"]), int(block["height"]))
            equation = document.shapes.add_equation(
                script,
                paragraph=anchor,
                base_unit=base_unit,
                size=size,
            )
            _add_caption(equation, block)
            bindings[block_id] = {
                "kind": kind,
                "paragraph_id": _paragraph_id(anchor),
                "latex_sha256": hashlib.sha256(latex.encode("utf-8")).hexdigest(),
            }
            continue

        if kind == "picture":
            payload, fmt = _image_bytes(block)
            media = document.media.add_image(payload, fmt)
            anchor = document.add_paragraph("")
            kwargs = {
                "width": int(block.get("width", 10000)),
                "height": int(block.get("height", 8000)),
                "treat_as_char": bool(block.get("inline", True)),
            }
            picture = anchor.add_picture(str(media.item_id), **kwargs)
            _add_caption(picture, block)
            bindings[block_id] = {
                "kind": kind,
                "paragraph_id": _paragraph_id(anchor),
                "asset_sha256": hashlib.sha256(payload).hexdigest(),
            }
            continue

        if kind == "page_break":
            paragraph = document.add_paragraph("")
            paragraph.element.set("pageBreak", "1")
            paragraph.section.mark_dirty()
            bindings[block_id] = {"kind": kind, "paragraph_id": _paragraph_id(paragraph)}
            continue

        if kind == "section_break":
            section = document.add_section()
            text = str(block.get("text") or "")
            paragraph = section.add_paragraph(text, inherit_style=False)
            bindings[block_id] = {
                "kind": kind,
                "paragraph_id": _paragraph_id(paragraph),
                "section_part": section.part_name,
            }
            continue

        raise AssertionError(kind)

    return {"bindings": bindings, "list_groups": list_groups}


def _resolve_bindings(path: Path, raw_bindings: dict[str, dict]) -> dict[str, dict]:
    mapped = build_document_map(path)["paragraphs"]
    by_id = {
        str(item["intrinsic_id"]): item
        for item in mapped
        if item.get("intrinsic_id") is not None
    }
    out = {}
    for block_id, binding in raw_bindings.items():
        paragraph = by_id.get(str(binding["paragraph_id"]))
        if paragraph is None:
            raise ValueError(f"composed block lost paragraph identity: {block_id}")
        out[block_id] = {
            **binding,
            "locator": paragraph["locator"],
            "section_index": paragraph["section_index"],
            "paragraph_index": paragraph["paragraph_index"],
        }
    return out


def _resolve_refs(value: Any, bindings: dict[str, dict]) -> Any:
    if isinstance(value, str) and value.startswith("$block:"):
        block_id = value.split(":", 1)[1]
        target = bindings.get(block_id)
        if target is None:
            raise ValueError(f"unknown block reference: {value}")
        return target["locator"]
    if isinstance(value, list):
        return [_resolve_refs(item, bindings) for item in value]
    if isinstance(value, dict):
        return {key: _resolve_refs(item, bindings) for key, item in value.items()}
    return value


def _preset_format_operations(
    preset: str,
    blocks: list[dict],
    bindings: dict[str, dict],
) -> list[dict]:
    spec = PRESETS[preset]
    ops: list[dict] = []
    for block in blocks:
        target = bindings[block["id"]]["locator"]
        kind = block["type"]
        run_format: dict = {}
        paragraph_format: dict = {}

        if kind == "title":
            run_format.update(spec.get("title_format", {}).get("run") or {})
            paragraph_format.update(spec.get("title_format", {}).get("paragraph") or {})
        elif kind == "heading":
            level = str(int(block.get("level", 1)))
            heading = spec.get("heading_format", {}).get(level) or {}
            run_format.update(heading.get("run") or {})
            paragraph_format.update(heading.get("paragraph") or {})
        elif kind in {"paragraph", "list_item"}:
            run_format.update(spec.get("body_format", {}).get("run") or {})
            paragraph_format.update(spec.get("body_format", {}).get("paragraph") or {})

        custom_run = block.get("run_format")
        if isinstance(custom_run, dict):
            run_format.update(custom_run)
        custom_para = block.get("paragraph_format")
        if isinstance(custom_para, dict):
            paragraph_format.update(custom_para)

        if run_format:
            ops.append({"op": "set_run_format", "target": target, "format": run_format})
        if paragraph_format:
            ops.append({"op": "set_paragraph_format", "target": target, "format": paragraph_format})
    return ops


def _table_finish_operations(
    candidate: Path,
    preset: str,
    blocks: list[dict],
    bindings: dict[str, dict],
) -> list[dict]:
    table_blocks = [block for block in blocks if block["type"] == "table"]
    if not table_blocks:
        return []
    mapped = build_advanced_table_map(candidate)
    by_index = {int(table["table_index"]): table for table in mapped.get("tables", [])}
    receipts = []

    for block in table_blocks:
        binding = bindings[block["id"]]
        table = by_index.get(int(binding["table_index"]))
        if table is None:
            raise ValueError(f"composed table lost identity: {block['id']}")
        config = dict(PRESETS[preset].get("table_format") or {})
        custom = block.get("table_format")
        if custom is not None and not isinstance(custom, dict):
            raise ValueError("table_format must be an object")
        config.update(dict(custom or {}))

        operations: list[dict] = []
        locator = table["locator"]
        page_break = config.get("page_break")
        if page_break:
            operations.append({"op": "set_table_page_break", "table": locator, "mode": str(page_break).upper()})
        border_color = config.get("border_color")
        if border_color:
            operations.append({"op": "set_table_borders", "table": locator, "color": str(border_color)})

        first_row_header = bool(config.get("first_row_header") or block.get("first_row_header"))
        repeat_header = bool(config.get("repeat_header", first_row_header))
        if first_row_header and repeat_header:
            operations.append({"op": "set_repeat_header", "table": locator, "row": 0, "enabled": True})

        if operations:
            receipt = apply_advanced_table_edits_atomic(
                candidate,
                operations,
                expected_revision=1,
                current_revision=1,
                validator=None,
            )
            receipts.append({
                "block_id": block["id"],
                "table": locator,
                "operations": operations,
                "receipt": receipt,
            })
    return receipts

def _publishing_operations(
    plan: dict,
    blocks: list[dict],
    bindings: dict[str, dict],
    list_groups: dict,
) -> list[dict]:
    ops: list[dict] = []
    for (kind, level, _list_id), block_ids in list_groups.items():
        ops.append({
            "op": "apply_list_format",
            "paragraphs": [bindings[block_id]["locator"] for block_id in block_ids],
            "kind": kind,
            "level": level,
        })

    for block in blocks:
        style = block.get("style")
        if style:
            ops.append({
                "op": "apply_named_style",
                "paragraph": bindings[block["id"]]["locator"],
                "style": style,
            })
        bookmark = block.get("bookmark")
        if bookmark:
            ops.append({
                "op": "add_bookmark",
                "paragraph": bindings[block["id"]]["locator"],
                "name": str(bookmark),
            })

    # Reference-bearing operations must resolve against the pre-TOC body.
    # Native TOC insertion can change paragraph ordinals, so compile it last.
    for raw in plan.get("post_operations", []) or []:
        ops.append(_resolve_refs(raw, bindings))

    publishing = plan.get("publishing") or {}
    toc = publishing.get("toc")
    if toc:
        cfg = {} if toc is True else dict(toc)
        ops.append({
            "op": "add_native_toc",
            "at_index": int(cfg.get("at_index", 0)),
            "title": str(cfg.get("title", "<제목 차례>")),
            "level": int(cfg.get("level", 3)),
        })
    return ops


def _setup_operations(plan: dict) -> list[dict]:
    ops = [dict(item) for item in PRESETS[plan["preset"]]["setup"]]
    ops.extend(dict(item) for item in (plan.get("setup") or []))
    publishing = plan.get("publishing") or {}
    if publishing.get("header") is not None:
        ops.append({"op": "set_header", "section_index": 0, "text": str(publishing["header"])})
    if publishing.get("footer") is not None:
        ops.append({"op": "set_footer", "section_index": 0, "text": str(publishing["footer"])})
    page_numbers = publishing.get("page_numbers")
    if page_numbers:
        cfg = {} if page_numbers is True else dict(page_numbers)
        ops.append({
            "op": "set_page_number",
            "section_index": int(cfg.get("section_index", 0)),
            "target": str(cfg.get("target", "footer")),
            "page_type": str(cfg.get("page_type", "BOTH")),
            "position": str(cfg.get("position", "BOTTOM_CENTER")),
            "prefix": str(cfg.get("prefix", "")),
            "suffix": str(cfg.get("suffix", "")),
        })
    return ops


def compose_document_plan(
    destination: Path,
    plan: dict,
    *,
    template_path: Path | None = None,
    validator: Callable[[Path], dict] | None = None,
) -> dict:
    normalized = _normalize_plan(plan)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=destination.stem + ".p321-compose-",
        suffix=".hwpx",
        dir=str(destination.parent),
    )
    os.close(fd)
    candidate = Path(tmp_name)
    stage_receipts: list[dict] = []

    try:
        if template_path is None:
            document = HwpxDocument.new()
        else:
            shutil.copy2(template_path, candidate)
            document = HwpxDocument.open(str(candidate))
        try:
            materialized = _materialize_blocks(document, normalized["blocks"])
            _save_document(document, candidate, candidate)
        finally:
            document.close()

        bindings = _resolve_bindings(candidate, materialized["bindings"])
        stage_receipts.append({
            "stage": "blocks",
            "block_count": len(bindings),
            "bindings_sha256": _sha(bindings),
        })

        setup_ops = _setup_operations(normalized)
        if setup_ops:
            setup_receipt = apply_document_setup_atomic(
                candidate,
                setup_ops,
                expected_revision=1,
                current_revision=1,
                validator=None,
            )
            stage_receipts.append({"stage": "setup", "operations": len(setup_ops), "receipt": setup_receipt})
            bindings = _resolve_bindings(candidate, materialized["bindings"])

        format_ops = _preset_format_operations(
            normalized["preset"], normalized["blocks"], bindings
        )
        if format_ops:
            format_receipt = apply_rich_formatting_atomic(
                candidate,
                format_ops,
                expected_revision=1,
                current_revision=1,
                validator=None,
            )
            stage_receipts.append({"stage": "formatting", "operations": len(format_ops), "receipt": format_receipt})
            bindings = _resolve_bindings(candidate, materialized["bindings"])

        table_finishing = _table_finish_operations(
            candidate,
            normalized["preset"],
            normalized["blocks"],
            bindings,
        )
        if table_finishing:
            stage_receipts.append({
                "stage": "table_finishing",
                "tables": len(table_finishing),
                "receipts": table_finishing,
            })
            bindings = _resolve_bindings(candidate, materialized["bindings"])

        publishing_ops = _publishing_operations(
            normalized,
            normalized["blocks"],
            bindings,
            materialized["list_groups"],
        )
        if publishing_ops:
            publishing_receipt = apply_structured_publishing_atomic(
                candidate,
                publishing_ops,
                expected_revision=1,
                current_revision=1,
                validator=None,
            )
            stage_receipts.append({
                "stage": "publishing",
                "operations": len(publishing_ops),
                "receipt": publishing_receipt,
            })
            bindings = _resolve_bindings(candidate, materialized["bindings"])

        annotation_ops = [
            _resolve_refs(item, bindings)
            for item in (normalized.get("annotations") or [])
        ]
        if annotation_ops:
            annotation_receipt = apply_annotation_apparatus_atomic(
                candidate,
                annotation_ops,
                expected_revision=1,
                current_revision=1,
                validator=None,
            )
            stage_receipts.append({
                "stage": "annotations",
                "operations": len(annotation_ops),
                "receipt": annotation_receipt,
            })
            bindings = _resolve_bindings(candidate, materialized["bindings"])

        validation = validator(candidate) if validator is not None else None
        document_map = build_document_map(candidate)
        result = {
            "schema": RECEIPT_SCHEMA,
            "plan_schema": PLAN_SCHEMA,
            "plan_sha256": _sha(normalized),
            "preset": normalized["preset"],
            "template_mode": "append" if template_path is not None else "blank",
            "block_count": len(normalized["blocks"]),
            "bindings": bindings,
            "stages": stage_receipts,
            "document": {
                "paragraph_count": document_map["paragraph_count"],
                "text_chars": document_map["text_chars"],
                "semantic_sha256": document_map["semantic_sha256"],
                "structure_sha256": document_map["structure_sha256"],
                "formatting_sha256": build_formatting_map(candidate)["formatting_sha256"],
                "table_structure_sha256": build_table_map(candidate)["table_structure_sha256"],
                "object_structure_sha256": build_object_map(candidate)["object_structure_sha256"],
                "equation_structure_sha256": build_equation_map(candidate)["equation_structure_sha256"],
                "document_setup_sha256": build_document_setup_map(candidate)["document_setup_sha256"],
                "structured_publishing_sha256": build_structured_publishing_map(candidate)["structured_publishing_sha256"],
                "annotation_apparatus_sha256": build_annotation_apparatus_map(candidate)["annotation_apparatus_sha256"],
            },
            "validation": validation,
            "atomic_commit": True,
            "authority": "STRUCTURAL_COMPOSITION_AUTHORITY",
            "dependency_order": [
                "block_materialization",
                "document_setup",
                "formatting",
                "table_finishing",
                "lists_styles_bookmarks_and_references",
                "native_toc",
                "annotations",
                "final_validation",
            ],
        }
        result["composition_sha256"] = _sha({
            "plan_sha256": result["plan_sha256"],
            "bindings": bindings,
            "document": result["document"],
        })
        os.replace(candidate, destination)
        return result
    except Exception:
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass
        raise
