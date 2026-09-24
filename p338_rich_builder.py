from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable

from p2_document import build_document_map
from p24_inline import apply_inline_edits_atomic, build_inline_map
from p27_tables import apply_table_edits_atomic
from p28_tables import build_table_map
from p29_objects import build_object_map
from p210_equations import build_equation_map
from p318_document_setup import build_document_setup_map
from p321_document_composer import validate_document_plan
from p323_advanced_tables import build_advanced_table_map
from p336r2_design import evaluate_generated_document


SCHEMA = "chatgpt-web-hwpx-mcp/p3.38/rich-builder/v1"
MAX_SECTIONS = 32
MAX_SMART_FIELDS = 100
MAX_SMART_OPERATIONS = 200

_PAGE_SETUP_FIELDS = {
    "paper_size", "width_mm", "height_mm", "orientation", "margins_mm",
    "margin_left_mm", "margin_right_mm", "margin_top_mm", "margin_bottom_mm",
    "header_margin_mm", "footer_margin_mm", "gutter_mm", "columns", "column_gap_mm",
}


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def rich_builder_contract() -> dict:
    return {
        "schema": SCHEMA,
        "phase": "P3.38",
        "product_goal": "RICH_MULTI_SECTION_REQUEST_TO_VALIDATED_NATIVE_HWPX_RESOURCE",
        "primary_tools": [
            "create_rich_document_and_deliver",
            "fill_template_intelligently_and_deliver",
            "evaluate_document_preview_readiness",
        ],
        "planning_tools": [
            "get_rich_document_builder_contract",
            "compile_rich_document_plan",
        ],
        "rich_plan": {
            "sections": {
                "max": MAX_SECTIONS,
                "page": "paper/orientation/margins/columns compiled to native P3.18 setup",
                "headers_footers": "per-section BOTH/ODD/EVEN text or structured content",
                "page_numbers": "per-section native page-number story",
                "blocks": [
                    "title", "paragraph", "heading", "list_item", "table",
                    "equation", "picture/image", "page_break",
                ],
            },
            "media": "bounded embedded image bytes through the existing P3.21 composer",
            "tables": "native table creation plus existing repeat-header/page-break/border finishing",
            "equations": "LaTeX input compiled through the existing equation authoring lane",
        },
        "intelligent_template_fill": {
            "strategies": ["PLACEHOLDER", "CELL_NAME", "LABEL_RIGHT", "LABEL_BELOW"],
            "matching": "exact or whitespace/terminal-colon normalized labels only; no fuzzy semantic guessing",
            "default_precedence": ["PLACEHOLDER", "CELL_NAME", "LABEL_RIGHT", "LABEL_BELOW"],
            "source_template_mutation": False,
            "outer_transaction": "clone -> plan -> apply -> validate -> atomic destination replace",
        },
        "preview_awareness": {
            "render_status": "NOT_RENDERED",
            "checks": [
                "native package validation when supplied",
                "section page/body geometry",
                "table mechanical/pagination checks",
                "picture/equation positive geometry and body-width overflow warnings",
                "presentation hierarchy signal",
            ],
            "authority": "STATIC_LAYOUT_RISK_SCREEN_NOT_RENDERED_VISUAL_PREVIEW",
        },
        "non_claims": [
            "No Hancom visual-render equivalence is inferred by preview readiness.",
            "No fuzzy form semantics are inferred from labels.",
            "No native semantic-role inference is loosened.",
        ],
    }


def _story_ops(kind: str, value: Any, section_index: int) -> list[dict]:
    if value is None:
        return []
    entries = value if isinstance(value, list) else [value]
    out: list[dict] = []
    for raw in entries:
        if isinstance(raw, str):
            cfg = {"text": raw}
        elif isinstance(raw, dict):
            cfg = dict(raw)
        else:
            raise ValueError(f"{kind} must be a string, object, or list")
        op = {
            "op": f"set_{kind}",
            "section_index": section_index,
            "page_type": str(cfg.get("page_type", "BOTH")).upper(),
        }
        if "content" in cfg:
            if not isinstance(cfg["content"], list):
                raise ValueError(f"{kind}.content must be a list")
            op["content"] = cfg["content"]
        else:
            op["text"] = str(cfg.get("text", ""))
        out.append(op)
    return out


def _page_number_ops(value: Any, section_index: int) -> list[dict]:
    if value is None or value is False:
        return []
    entries = value if isinstance(value, list) else [({} if value is True else value)]
    out: list[dict] = []
    for raw in entries:
        if not isinstance(raw, dict):
            raise ValueError("page_numbers must be true, an object, or a list")
        cfg = dict(raw)
        out.append({
            "op": "set_page_number",
            "section_index": section_index,
            "target": str(cfg.get("target", "footer")),
            "page_type": str(cfg.get("page_type", "BOTH")).upper(),
            "format": str(cfg.get("format", "page")),
            "position": str(cfg.get("position", "BOTTOM_CENTER")).upper(),
            "align": str(cfg.get("align", "CENTER")).upper(),
            "prefix": str(cfg.get("prefix", "")),
            "suffix": str(cfg.get("suffix", "")),
            **({"format_type": str(cfg["format_type"])} if cfg.get("format_type") is not None else {}),
        })
    return out


def compile_rich_document_plan(rich_plan: dict) -> dict:
    if not isinstance(rich_plan, dict):
        raise ValueError("rich_plan must be an object")
    sections = rich_plan.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError("rich_plan.sections must be a non-empty list")
    if len(sections) > MAX_SECTIONS:
        raise ValueError(f"rich plan exceeds {MAX_SECTIONS} sections")

    flattened: list[dict] = []
    setup_ops: list[dict] = [dict(x) for x in (rich_plan.get("setup") or [])]
    used_explicit_ids: set[str] = set()

    publishing = dict(rich_plan.get("publishing") or {})
    default_header = publishing.pop("header", None)
    default_footer = publishing.pop("footer", None)
    default_page_numbers = publishing.pop("page_numbers", None)

    for section_index, raw_section in enumerate(sections):
        if not isinstance(raw_section, dict):
            raise ValueError("each rich section must be an object")
        section = dict(raw_section)
        blocks = section.get("blocks", [])
        if not isinstance(blocks, list):
            raise ValueError("section.blocks must be a list")

        if section_index:
            marker_id = f"__p338_section_{section_index + 1}"
            if marker_id in used_explicit_ids:
                raise ValueError("reserved P3.38 section marker id collision")
            flattened.append({
                "id": marker_id,
                "type": "section_break",
                "text": str(section.get("opening_text", "")),
            })
            used_explicit_ids.add(marker_id)

        for raw_block in blocks:
            if not isinstance(raw_block, dict):
                raise ValueError("each rich block must be an object")
            block = dict(raw_block)
            if block.get("type") == "image":
                block["type"] = "picture"
            explicit_id = block.get("id")
            if explicit_id is not None:
                value = str(explicit_id)
                if value in used_explicit_ids:
                    raise ValueError(f"duplicate rich block id: {value}")
                used_explicit_ids.add(value)
            flattened.append(block)

        page = section.get("page")
        if page is not None:
            if not isinstance(page, dict):
                raise ValueError("section.page must be an object")
            cfg = {k: v for k, v in page.items() if k in _PAGE_SETUP_FIELDS}
            if cfg:
                setup_ops.append({"op": "set_page_setup", "section_index": section_index, **cfg})

        setup_ops.extend(_story_ops(
            "header",
            section.get("headers", section.get("header", default_header if section_index == 0 else None)),
            section_index,
        ))
        setup_ops.extend(_story_ops(
            "footer",
            section.get("footers", section.get("footer", default_footer if section_index == 0 else None)),
            section_index,
        ))
        setup_ops.extend(_page_number_ops(
            section.get("page_numbers", default_page_numbers if section_index == 0 else None),
            section_index,
        ))

        start_numbering = section.get("start_numbering")
        if start_numbering is not None:
            if not isinstance(start_numbering, dict):
                raise ValueError("section.start_numbering must be an object")
            setup_ops.append({
                "op": "set_section_start_numbering",
                "section_index": section_index,
                **dict(start_numbering),
            })

        for raw_op in section.get("setup", []) or []:
            if not isinstance(raw_op, dict):
                raise ValueError("section.setup operations must be objects")
            op = dict(raw_op)
            op.setdefault("section_index", section_index)
            setup_ops.append(op)

    if not flattened:
        raise ValueError("rich plan must contain at least one block")

    plan = {
        "preset": str(rich_plan.get("preset", "polished-report")),
        "document": dict(rich_plan.get("document") or {}),
        "setup": setup_ops,
        "blocks": flattened,
    }
    if publishing:
        plan["publishing"] = publishing
    if rich_plan.get("annotations") is not None:
        plan["annotations"] = list(rich_plan.get("annotations") or [])
    if rich_plan.get("post_operations") is not None:
        plan["post_operations"] = list(rich_plan.get("post_operations") or [])

    checked = validate_document_plan(plan)
    receipt = {
        "schema": "chatgpt-web-hwpx-mcp/p3.38/rich-plan-compile/v1",
        "phase": "P3.38",
        "section_count": len(sections),
        "block_count": checked["block_count"],
        "block_counts": checked["block_counts"],
        "setup_operation_count": len(setup_ops),
        "plan": plan,
        "plan_sha256": checked["plan_sha256"],
        "authority": "COMPILED_TO_EXISTING_NATIVE_AUTHORING_PRIMITIVES",
    }
    receipt["compile_sha256"] = _sha({
        "section_count": receipt["section_count"],
        "plan_sha256": receipt["plan_sha256"],
        "setup_operation_count": receipt["setup_operation_count"],
    })
    return receipt


def _label_normalize(value: Any) -> str:
    return " ".join(str(value or "").strip().rstrip(":：").split())


def _base_field_name(key: str) -> str:
    value = str(key).strip()
    pairs = [("{{", "}}"), ("<<", ">>"), ("[[", "]]")]
    for left, right in pairs:
        if value.startswith(left) and value.endswith(right) and len(value) > len(left) + len(right):
            return value[len(left):-len(right)].strip()
    return value


def _placeholder_tokens(key: str, spec: dict) -> list[str]:
    explicit = spec.get("placeholders")
    if explicit is not None:
        if not isinstance(explicit, list) or not explicit:
            raise ValueError("field placeholders must be a non-empty list")
        return [str(x) for x in explicit]
    raw = str(key)
    base = _base_field_name(raw)
    if raw != base:
        return [raw]
    return [f"{{{{{base}}}}}", f"<<{base}>>", f"[[{base}]]"]


def _field_aliases(key: str, spec: dict) -> list[str]:
    values = [spec.get("label"), _base_field_name(key)]
    aliases = spec.get("aliases", [])
    if aliases is not None:
        if not isinstance(aliases, list):
            raise ValueError("field aliases must be a list")
        values.extend(aliases)
    out: list[str] = []
    for value in values:
        norm = _label_normalize(value)
        if norm and norm not in out:
            out.append(norm)
    return out


def _inline_candidates(inline: dict, tokens: list[str], value: str) -> list[dict]:
    out: list[dict] = []
    for paragraph in inline.get("paragraphs", []):
        text = str(paragraph.get("inline_text") or "")
        for token in tokens:
            if not token:
                continue
            start = 0
            while True:
                index = text.find(token, start)
                if index < 0:
                    break
                out.append({
                    "strategy": "PLACEHOLDER",
                    "target_key": ["inline", paragraph["locator"], index, index + len(token)],
                    "operation": {
                        "op": "replace_inline_text",
                        "target": paragraph["locator"],
                        "start": index,
                        "end": index + len(token),
                        "text": value,
                        "expected_text": token,
                    },
                    "evidence": {"token": token, "paragraph": paragraph["locator"]},
                })
                start = index + len(token)
    return out


def _cell_name_candidates(tables: dict, aliases: list[str], value: str, overwrite: bool) -> list[dict]:
    out: list[dict] = []
    aliases_set = set(aliases)
    for table in tables.get("tables", []):
        for cell in table.get("cells", []):
            if _label_normalize(cell.get("name")) not in aliases_set:
                continue
            current = str(cell.get("text") or "")
            if current and not overwrite:
                continue
            out.append({
                "strategy": "CELL_NAME",
                "target_key": ["cell", table["locator"], cell["locator"]],
                "operation": {
                    "op": "set_cell_text",
                    "table": table["locator"],
                    "cell": cell["locator"],
                    "text": value,
                },
                "evidence": {"cell_name": cell.get("name"), "cell": cell["locator"]},
            })
    return out


def _label_cell_candidates(
    tables: dict,
    aliases: list[str],
    value: str,
    direction: str,
    overwrite: bool,
) -> list[dict]:
    out: list[dict] = []
    aliases_set = set(aliases)
    for table in tables.get("tables", []):
        cells = list(table.get("cells", []))
        by_address = {(int(c["row"]), int(c["col"])): c for c in cells}
        for label in cells:
            if _label_normalize(label.get("text")) not in aliases_set:
                continue
            row, col = int(label["row"]), int(label["col"])
            if direction == "RIGHT":
                address = (row, col + int(label.get("col_span") or 1))
            else:
                address = (row + int(label.get("row_span") or 1), col)
            target = by_address.get(address)
            if target is None:
                continue
            current = str(target.get("text") or "")
            if current and not overwrite:
                continue
            strategy = f"LABEL_{direction}"
            out.append({
                "strategy": strategy,
                "target_key": ["cell", table["locator"], target["locator"]],
                "operation": {
                    "op": "set_cell_text",
                    "table": table["locator"],
                    "cell": target["locator"],
                    "text": value,
                },
                "evidence": {
                    "label": label.get("text"),
                    "label_cell": label["locator"],
                    "target_cell": target["locator"],
                },
            })
    return out


def plan_intelligent_template_fill(
    path: Path | str,
    values: dict[str, str],
    *,
    field_specs: dict[str, dict] | None = None,
    require_each: bool = True,
    require_unique: bool = True,
) -> dict:
    path = Path(path)
    if not isinstance(values, dict) or not values:
        raise ValueError("template fill values must be a non-empty object")
    if len(values) > MAX_SMART_FIELDS:
        raise ValueError(f"intelligent template fill exceeds {MAX_SMART_FIELDS} fields")
    field_specs = dict(field_specs or {})
    unknown_specs = sorted(set(field_specs) - set(values))
    if unknown_specs:
        raise ValueError("field_specs contains keys absent from values: " + ", ".join(unknown_specs[:10]))

    inline = build_inline_map(path)
    tables = build_table_map(path)
    fields: dict[str, dict] = {}
    inline_ops: list[dict] = []
    table_ops: list[dict] = []
    occupied: dict[tuple, str] = {}

    for raw_key, raw_value in values.items():
        key = str(raw_key)
        value = str(raw_value)
        if not key or len(key) > 256:
            raise ValueError("field keys must be 1..256 characters")
        if len(value) > 10000:
            raise ValueError("field replacement exceeds 10000 characters")
        spec = dict(field_specs.get(raw_key) or field_specs.get(key) or {})
        strategies = spec.get(
            "strategies",
            ["PLACEHOLDER", "CELL_NAME", "LABEL_RIGHT", "LABEL_BELOW"],
        )
        if not isinstance(strategies, list) or not strategies:
            raise ValueError("field strategies must be a non-empty list")
        strategies = [str(x).upper() for x in strategies]
        allowed = {"PLACEHOLDER", "CELL_NAME", "LABEL_RIGHT", "LABEL_BELOW"}
        if any(x not in allowed for x in strategies):
            raise ValueError("unsupported intelligent fill strategy")
        aliases = _field_aliases(key, spec)
        overwrite = bool(spec.get("overwrite", False))
        selected: list[dict] = []

        for strategy in strategies:
            if strategy == "PLACEHOLDER":
                candidates = _inline_candidates(inline, _placeholder_tokens(key, spec), value)
            elif strategy == "CELL_NAME":
                candidates = _cell_name_candidates(tables, aliases, value, overwrite)
            elif strategy == "LABEL_RIGHT":
                candidates = _label_cell_candidates(tables, aliases, value, "RIGHT", overwrite)
            else:
                candidates = _label_cell_candidates(tables, aliases, value, "BELOW", overwrite)
            if candidates:
                selected = candidates
                break

        allow_multiple = bool(spec.get("allow_multiple", False))
        if selected and require_unique and not allow_multiple and len(selected) != 1:
            raise ValueError(f"intelligent template field is ambiguous: {key}")
        if selected and not allow_multiple:
            selected = selected[:1]
        if not selected:
            fields[key] = {"status": "UNRESOLVED", "strategy": None, "targets": []}
            continue

        target_records = []
        for candidate in selected:
            target_key = tuple(candidate["target_key"])
            prior = occupied.get(target_key)
            if prior is not None and prior != key:
                raise ValueError(f"template fill target collision: {prior} / {key}")
            occupied[target_key] = key
            op = candidate["operation"]
            if candidate["strategy"] == "PLACEHOLDER":
                inline_ops.append(op)
            else:
                table_ops.append(op)
            target_records.append(candidate["evidence"])
        fields[key] = {
            "status": "RESOLVED",
            "strategy": selected[0]["strategy"],
            "targets": target_records,
        }

    unresolved = [key for key, item in fields.items() if item["status"] != "RESOLVED"]
    if require_each and unresolved:
        raise ValueError("template fields unresolved: " + ", ".join(unresolved[:10]))
    operation_count = len(inline_ops) + len(table_ops)
    if operation_count == 0:
        raise ValueError("intelligent template fill produced no operations")
    if operation_count > MAX_SMART_OPERATIONS:
        raise ValueError(f"intelligent template fill exceeds {MAX_SMART_OPERATIONS} operations")

    payload = {
        "fields": fields,
        "inline_operations": inline_ops,
        "table_operations": table_ops,
        "inline_structure_sha256": inline.get("inline_structure_sha256"),
        "table_structure_sha256": tables.get("table_structure_sha256"),
    }
    return {
        "schema": "chatgpt-web-hwpx-mcp/p3.38/intelligent-fill-plan/v1",
        "fields": fields,
        "resolved_fields": sum(item["status"] == "RESOLVED" for item in fields.values()),
        "unresolved_fields": unresolved,
        "operation_count": operation_count,
        "inline_operations": inline_ops,
        "table_operations": table_ops,
        "plan_sha256": _sha(payload),
        "authority": "EXACT_STRUCTURAL_FORM_RESOLUTION_NO_FUZZY_SEMANTIC_GUESSING",
    }


def intelligent_fill_atomic(
    template_path: Path | str,
    destination: Path | str,
    values: dict[str, str],
    *,
    field_specs: dict[str, dict] | None = None,
    require_each: bool = True,
    require_unique: bool = True,
    validator: Callable[[Path], dict] | None = None,
) -> dict:
    template_path = Path(template_path)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=destination.stem + ".p338-fill-",
        suffix=".hwpx",
        dir=str(destination.parent),
    )
    os.close(fd)
    candidate = Path(tmp_name)
    try:
        shutil.copy2(template_path, candidate)
        before_sha = hashlib.sha256(template_path.read_bytes()).hexdigest()
        plan = plan_intelligent_template_fill(
            candidate,
            values,
            field_specs=field_specs,
            require_each=require_each,
            require_unique=require_unique,
        )
        stage_receipts: list[dict] = []
        if plan["inline_operations"]:
            receipt = apply_inline_edits_atomic(
                candidate,
                plan["inline_operations"],
                expected_revision=1,
                current_revision=1,
                validator=None,
            )
            stage_receipts.append({"stage": "inline", "receipt": receipt})
        if plan["table_operations"]:
            receipt = apply_table_edits_atomic(
                candidate,
                plan["table_operations"],
                expected_revision=1,
                current_revision=1,
                validator=None,
            )
            stage_receipts.append({"stage": "table", "receipt": receipt})

        validation = validator(candidate) if validator is not None else None
        after_document = build_document_map(candidate)
        after_inline = build_inline_map(candidate)
        after_tables = build_table_map(candidate)
        receipt = {
            "schema": "chatgpt-web-hwpx-mcp/p3.38/intelligent-fill-receipt/v1",
            "plan_sha256": plan["plan_sha256"],
            "fields": plan["fields"],
            "resolved_fields": plan["resolved_fields"],
            "operation_count": plan["operation_count"],
            "stages": stage_receipts,
            "source_template_sha256": before_sha,
            "source_template_mutated": hashlib.sha256(template_path.read_bytes()).hexdigest() != before_sha,
            "semantic_sha256_after": after_document["semantic_sha256"],
            "structure_sha256_after": after_document["structure_sha256"],
            "inline_structure_sha256_after": after_inline["inline_structure_sha256"],
            "table_structure_sha256_after": after_tables["table_structure_sha256"],
            "validation": validation,
            "atomic_commit": True,
            "authority": "CLONE_PLAN_APPLY_VALIDATE_COMMIT",
        }
        if receipt["source_template_mutated"]:
            raise RuntimeError("source template changed during intelligent fill")
        receipt["fill_sha256"] = _sha(receipt)
        os.replace(candidate, destination)
        return receipt
    finally:
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass


def evaluate_preview_readiness(
    path: Path | str,
    *,
    mode: str = "POLISHED_REPORT",
    validator: Callable[[Path], dict] | None = None,
) -> dict:
    path = Path(path)
    validation = validator(path) if validator is not None else None
    setup = build_document_setup_map(path)
    tables = build_advanced_table_map(path)
    objects = build_object_map(path)
    equations = build_equation_map(path)
    mechanical = evaluate_generated_document(path, mode)

    gates: list[dict] = []
    section_body: dict[int, tuple[int, int]] = {}
    for section in setup.get("sections", []):
        index = int(section["section_index"])
        width = int(section["page"].get("width") or 0)
        height = int(section["page"].get("height") or 0)
        margins = section.get("margins") or {}
        body_width = width - int(margins.get("left") or 0) - int(margins.get("right") or 0) - int(margins.get("gutter") or 0)
        body_height = height - int(margins.get("top") or 0) - int(margins.get("bottom") or 0)
        section_body[index] = (body_width, body_height)
        ok = width > 0 and height > 0 and body_width > 0 and body_height > 0
        gates.append({
            "gate": "SECTION_PAGE_GEOMETRY",
            "section_index": index,
            "status": "PASS" if ok else "FAIL",
            "evidence": {
                "page": [width, height],
                "body": [body_width, body_height],
            },
        })

    for picture in objects.get("pictures", []):
        section_index = int(picture.get("section_index") or 0)
        width = int(picture.get("width") or 0)
        height = int(picture.get("height") or 0)
        body_width = section_body.get(section_index, (0, 0))[0]
        if width <= 0 or height <= 0:
            status = "FAIL"
        elif body_width > 0 and width > body_width:
            status = "WARN"
        else:
            status = "PASS"
        gates.append({
            "gate": "PICTURE_GEOMETRY",
            "locator": picture.get("locator"),
            "status": status,
            "evidence": {"size": [width, height], "section_body_width": body_width},
        })

    for equation in equations.get("equations", []):
        section_index = int(equation.get("section_index") or 0)
        width = int(equation.get("width") or 0)
        height = int(equation.get("height") or 0)
        body_width = section_body.get(section_index, (0, 0))[0]
        if width <= 0 or height <= 0:
            status = "FAIL"
        elif body_width > 0 and width > body_width:
            status = "WARN"
        else:
            status = "PASS"
        gates.append({
            "gate": "EQUATION_GEOMETRY",
            "locator": equation.get("locator"),
            "status": status,
            "evidence": {"size": [width, height], "section_body_width": body_width},
        })

    mechanical_status = str(mechanical.get("mechanical_verdict") or "HOLD")
    gates.append({
        "gate": "P3.36_MECHANICAL_DESIGN_CHECKS",
        "status": mechanical_status,
        "evidence": {
            "tables": tables.get("table_count", 0),
            "table_summary": mechanical.get("table_summary"),
        },
    })

    statuses = [item["status"] for item in gates]
    if "FAIL" in statuses:
        verdict = "FAIL"
    elif "HOLD" in statuses:
        verdict = "HOLD"
    elif "WARN" in statuses:
        verdict = "PASS_WITH_WARNINGS"
    else:
        verdict = "PASS"

    result = {
        "schema": "chatgpt-web-hwpx-mcp/p3.38/preview-readiness/v1",
        "phase": "P3.38",
        "verdict": verdict,
        "render_status": "NOT_RENDERED",
        "visual_equivalence": "NOT_CLAIMED",
        "validation": validation,
        "section_count": setup.get("section_count", 0),
        "table_count": tables.get("table_count", 0),
        "picture_count": objects.get("picture_count", 0),
        "equation_count": equations.get("equation_count", 0),
        "gates": gates,
        "mechanical": mechanical,
        "authority": "STATIC_LAYOUT_RISK_SCREEN_NOT_RENDERED_VISUAL_PREVIEW",
    }
    result["preview_readiness_sha256"] = _sha(result)
    return result
