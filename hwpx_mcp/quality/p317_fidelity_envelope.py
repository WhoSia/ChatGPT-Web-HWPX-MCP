from __future__ import annotations

import hashlib
import json
from typing import Any


CONTRACT_SCHEMA = "chatgpt-web-hwpx-mcp/production-fidelity-contract/p3.17/v1"
ENVELOPE_SCHEMA = "chatgpt-web-hwpx-mcp/edit-fidelity-envelope/p3.17/v1"

VERSION_INDEXED_RENDERER = {
    "name": "Hancom Hangul",
    "version": "13.0.0.3622",
    "executable_sha256": "91541f8c16e592516d0265c795b565a14a2cacef0b64f616b0626f54f3d3ece2",
    "authority": "HANCOM_VERSION_INDEXED_EXACT_RENDER_AUTHORITY",
}

# Product-facing edit classes.  "structural" means the MCP can make and
# deterministically receipt the edit without a renderer.  "render" records
# whether this concrete class has earned native-Hancom render certification.
EDIT_CLASSES: dict[str, dict[str, Any]] = {
    "text_content": {
        "ops": {
            "replace_text", "replace_paragraph_text", "insert_paragraph",
            "append_paragraph", "delete_paragraph",
        },
        "structural": "SUPPORTED",
        "render": "CERTIFICATION_PENDING",
        "structural_dimensions": ["text_content", "paragraph_topology"],
    },
    "run_format": {
        "ops": {
            "set_run_format", "set_range_format", "copy_run_format",
            "normalize_formatting",
        },
        "structural": "SUPPORTED",
        "render": "CERTIFICATION_PENDING",
        "structural_dimensions": ["header_style", "run_style_refs"],
    },
    "paragraph_format": {
        "ops": {"set_paragraph_format", "copy_paragraph_format"},
        "structural": "SUPPORTED",
        "render": "CERTIFICATION_PENDING",
        "structural_dimensions": ["header_style", "paragraph_style_refs"],
    },
    "table": {
        "ops": {
            "create_table", "delete_table", "set_cell_text", "set_cell_shading",
            "set_cell_borders", "set_cell_properties", "set_cell_margin",
            "set_cell_size", "set_cell_border_fill", "set_cell_gradient",
        },
        "structural": "SUPPORTED",
        "render": "CERTIFICATION_PENDING",
        "structural_dimensions": ["table_topology", "table_format", "table_geometry"],
    },
    "object_picture": {
        "ops": {
            "insert_picture", "replace_picture", "remove_picture",
            "resize_picture", "set_picture_position",
        },
        "structural": "SUPPORTED",
        "render": "CERTIFICATION_PENDING",
        "structural_dimensions": ["object_topology", "object_geometry", "media_custody"],
    },
    "textbox": {
        "ops": {"insert_textbox"},
        "structural": "SUPPORTED",
        "render": "CERTIFICATION_PENDING",
        "structural_dimensions": ["object_topology", "object_geometry", "text_content"],
    },
    "equation": {
        "ops": {
            "insert_equation", "replace_equation", "remove_equation",
            "resize_equation",
        },
        "structural": "SUPPORTED",
        "render": "CERTIFICATION_PENDING",
        "structural_dimensions": ["equation_topology", "equation_geometry", "equation_script"],
    },
    "page_margin_geometry": {
        "ops": {"set_page_margin"},
        "structural": "SUPPORTED",
        "render": "BOUNDARY_CERTIFIED",
        "structural_dimensions": ["page_geometry"],
    },
    "page_composition": {
        "ops": {"set_page_setup", "set_page_size", "set_columns"},
        "structural": "SUPPORTED",
        "render": "CERTIFICATION_PENDING",
        "structural_dimensions": ["page_geometry", "column_layout"],
    },
    "header_footer": {
        "ops": {"set_header", "set_footer", "remove_header", "remove_footer"},
        "structural": "SUPPORTED",
        "render": "CERTIFICATION_PENDING",
        "structural_dimensions": ["section_story"],
    },
    "page_numbering": {
        "ops": {
            "set_page_number", "restart_page_number", "set_section_start_numbering",
        },
        "structural": "SUPPORTED",
        "render": "CERTIFICATION_PENDING",
        "structural_dimensions": ["section_story", "numbering_controls"],
    },
    "section_structure": {
        "ops": {"add_section", "remove_section"},
        "structural": "SUPPORTED",
        "render": "CERTIFICATION_PENDING",
        "structural_dimensions": ["section_topology", "page_geometry"],
    },
    "list_numbering": {
        "ops": {"apply_list_format"},
        "structural": "SUPPORTED",
        "render": "CERTIFICATION_PENDING",
        "structural_dimensions": ["paragraph_style_refs", "list_numbering"],
    },
    "named_styles": {
        "ops": {"apply_named_style"},
        "structural": "SUPPORTED",
        "render": "CERTIFICATION_PENDING",
        "structural_dimensions": ["paragraph_style_refs", "run_style_refs"],
    },
    "captions": {
        "ops": {"set_caption"},
        "structural": "SUPPORTED",
        "render": "CERTIFICATION_PENDING",
        "structural_dimensions": ["object_topology", "caption_story"],
    },
    "cross_reference": {
        "ops": {"add_bookmark", "add_page_crossref"},
        "structural": "SUPPORTED",
        "render": "CERTIFICATION_PENDING",
        "structural_dimensions": ["reference_fields", "paragraph_anchors"],
    },
    "table_of_contents": {
        "ops": {"add_native_toc", "mark_toc_dirty"},
        "structural": "SUPPORTED",
        "render": "CERTIFICATION_PENDING",
        "structural_dimensions": ["reference_fields", "paragraph_anchors", "section_topology"],
    },
    "outline_hierarchy": {
        "ops": {"set_outline_level", "add_heading"},
        "structural": "SUPPORTED",
        "render": "CERTIFICATION_PENDING",
        "structural_dimensions": ["paragraph_style_refs", "outline_hierarchy"],
    },
    "footnote_endnote": {
        "ops": {"add_footnote", "add_endnote"},
        "structural": "SUPPORTED",
        "render": "CERTIFICATION_PENDING",
        "structural_dimensions": ["annotation_story", "reference_fields"],
    },
    "memo_comment": {
        "ops": {"add_memo", "remove_memo"},
        "structural": "SUPPORTED",
        "render": "CERTIFICATION_PENDING",
        "structural_dimensions": ["annotation_story", "reference_fields"],
    },
    "index_mark": {
        "ops": {"add_index_mark"},
        "structural": "SUPPORTED",
        "render": "CERTIFICATION_PENDING",
        "structural_dimensions": ["index_marks", "paragraph_anchors"],
    },
    "reference_navigation": {
        "ops": {"add_hyperlink"},
        "structural": "SUPPORTED",
        "render": "CERTIFICATION_PENDING",
        "structural_dimensions": ["reference_fields", "paragraph_anchors"],
    },
    "rich_reference_fields": {
        "ops": {
            "add_date_field", "add_path_field", "add_mail_merge_field",
            "add_proofreading_mark",
        },
        "structural": "SUPPORTED",
        "render": "CERTIFICATION_PENDING",
        "structural_dimensions": ["reference_fields", "cached_field_text"],
    },
    "tracked_review": {
        "ops": {"tracked_insert", "tracked_delete", "tracked_replace"},
        "structural": "SUPPORTED",
        "render": "CERTIFICATION_PENDING",
        "structural_dimensions": ["tracked_changes", "paragraph_anchors"],
    },
    "form_fields": {
        "ops": {"add_form_field", "fill_form_field"},
        "structural": "SUPPORTED",
        "render": "CERTIFICATION_PENDING",
        "structural_dimensions": ["form_fields", "field_text"],
    },
    "check_box_controls": {
        "ops": {"add_check_box", "set_check_box"},
        "structural": "SUPPORTED",
        "render": "CERTIFICATION_PENDING",
        "structural_dimensions": ["form_controls"],
    },
    "text_highlight": {
        "ops": {"add_highlight"},
        "structural": "SUPPORTED",
        "render": "CERTIFICATION_PENDING",
        "structural_dimensions": ["text_markers", "paragraph_anchors"],
    },
    "document_metadata": {
        "ops": {"set_document_metadata"},
        "structural": "SUPPORTED",
        "render": "CERTIFICATION_PENDING",
        "structural_dimensions": ["package_metadata"],
    },
    "no_op_replay": {
        "ops": {"no_op"},
        "structural": "SUPPORTED",
        "render": "EXACT_CERTIFIED",
        "structural_dimensions": [],
    },
}

OP_TO_CLASS = {
    op: class_name
    for class_name, spec in EDIT_CLASSES.items()
    for op in spec["ops"]
}


def _sha(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def production_fidelity_contract() -> dict:
    rows = []
    for name, spec in EDIT_CLASSES.items():
        render = spec["render"]
        if render == "EXACT_CERTIFIED":
            runtime_ceiling = "VERSION_INDEXED_EXACT"
        elif render == "BOUNDARY_CERTIFIED":
            runtime_ceiling = "VERSION_INDEXED_BOUNDARY"
        else:
            runtime_ceiling = "STRUCTURAL_AUTHORITY_ONLY"
        rows.append({
            "edit_class": name,
            "operations": sorted(spec["ops"]),
            "structural_support": spec["structural"],
            "render_certification": render,
            "runtime_ceiling": runtime_ceiling,
            "structural_dimensions": list(spec["structural_dimensions"]),
        })

    contract = {
        "schema": CONTRACT_SCHEMA,
        "renderer": dict(VERSION_INDEXED_RENDERER),
        "edit_classes": rows,
        "default_unknown_operation": "UNCLASSIFIED_REQUIRES_REVIEW",
        "cross_version_authority": "DEFERRED",
        "semantics": (
            "Exact claims are version-indexed. Structural support does not imply "
            "native-render exactness unless the edit class is explicitly certified."
        ),
    }
    contract["contract_sha256"] = _sha(contract)
    return contract


def classify_edit_operation(operation: dict) -> dict:
    if not isinstance(operation, dict):
        raise ValueError("edit operation must be an object")
    op = str(operation.get("op") or "").strip()
    if not op:
        raise ValueError("edit operation requires op")

    class_name = OP_TO_CLASS.get(op)
    if class_name is None:
        return {
            "op": op,
            "edit_class": None,
            "structural_support": "UNKNOWN",
            "render_certification": "NONE",
            "authority_ceiling": "UNCLASSIFIED_REQUIRES_REVIEW",
            "requires_native_render_check": True,
        }

    spec = EDIT_CLASSES[class_name]
    render = spec["render"]
    if render == "EXACT_CERTIFIED":
        ceiling = "VERSION_INDEXED_EXACT"
        native = False
    elif render == "BOUNDARY_CERTIFIED":
        ceiling = "VERSION_INDEXED_BOUNDARY"
        native = False
    else:
        ceiling = "STRUCTURAL_AUTHORITY_ONLY"
        native = True

    return {
        "op": op,
        "edit_class": class_name,
        "structural_support": spec["structural"],
        "render_certification": render,
        "authority_ceiling": ceiling,
        "structural_dimensions": list(spec["structural_dimensions"]),
        "requires_native_render_check": native,
    }


def assess_edit_fidelity_envelope(operations: list[dict]) -> dict:
    if not isinstance(operations, list) or not operations:
        raise ValueError("operations must be a non-empty list")
    if len(operations) > 200:
        raise ValueError("too many operations")

    items = [classify_edit_operation(op) for op in operations]
    ceilings = {item["authority_ceiling"] for item in items}
    requires_native = any(item["requires_native_render_check"] for item in items)

    if "UNCLASSIFIED_REQUIRES_REVIEW" in ceilings:
        overall = "UNCLASSIFIED_REQUIRES_REVIEW"
    elif requires_native:
        overall = "STRUCTURAL_AUTHORITY_ONLY"
    elif "VERSION_INDEXED_BOUNDARY" in ceilings:
        overall = "VERSION_INDEXED_BOUNDARY"
    else:
        overall = "VERSION_INDEXED_EXACT"

    result = {
        "schema": ENVELOPE_SCHEMA,
        "operation_count": len(items),
        "items": items,
        "overall_authority_ceiling": overall,
        "native_render_check_required": requires_native,
        "renderer_scope": dict(VERSION_INDEXED_RENDERER),
        "cross_version_authority": "DEFERRED",
    }
    result["assessment_sha256"] = _sha(result)
    return result
