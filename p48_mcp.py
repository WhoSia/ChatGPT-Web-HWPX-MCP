from __future__ import annotations

import hashlib
import json

from mcp.types import ToolAnnotations

from p2_document import build_document_map
from p22_formatting import build_formatting_map
from p24_inline import build_inline_map
from p28_tables import apply_table_edits_atomic, build_table_map
from p29_objects import build_object_map
from p210_equations import apply_equation_edits_atomic, build_equation_map
from p321_document_composer import compose_document_plan
from p325_drawing_layer import apply_drawing_layer_atomic, build_drawing_layer_map
from p326_drawing_style import apply_drawing_style_atomic, build_drawing_style_map
from p338_rich_builder import evaluate_preview_readiness
from p46_native_authoring import compile_native_authoring_bundle
from p47_native_authoring import compile_unified_authoring_plan as compile_unified_authoring_plan_kernel
from p49_visual_conformance import audit_materialized_visuals, certify_visual_plans
from p48_components import (
    component_authoring_contract,
    compile_document_components as compile_document_components_kernel,
    distribution_quickstart_contract,
    plan_component_repairs as plan_component_repairs_kernel,
)


def _created_rect_locator(path, shape_id: str) -> str:
    mapped = build_drawing_layer_map(path)
    found = next(
        (
            item for item in mapped["objects"]
            if item["kind"] == "rect"
            and str(item.get("id") or item.get("instid") or "") == str(shape_id)
        ),
        None,
    )
    if found is None:
        raise ValueError(f"created textbox/rectangle could not be rebound: {shape_id}")
    return str(found["locator"])


def _style_textbox(path, locator: str, *, fill: str = "#FFFFFF", stroke: str = "#FFFFFF") -> list[dict]:
    receipt = apply_drawing_style_atomic(
        path,
        [
            {"op": "set_shape_fill", "drawing": locator, "color": fill},
            {"op": "set_shape_stroke", "drawing": locator, "color": stroke, "width": 33},
        ],
        expected_revision=1,
        current_revision=1,
        validator=None,
    )
    return list(receipt["receipts"])


def _insert_filled_rectangle(
    path,
    anchor: str,
    *,
    x: int,
    y: int,
    width: int,
    height: int,
    fill: str,
    stroke: str,
    z_order: int = 1,
) -> dict:
    created = apply_drawing_layer_atomic(
        path,
        [{
            "op": "insert_rectangle",
            "anchor": anchor,
            "width": int(width),
            "height": int(height),
            "horizontal_offset": int(x),
            "vertical_offset": int(y),
            "horz_rel_to": "PARA",
            "vert_rel_to": "PARA",
            "z_order": int(z_order),
        }],
        expected_revision=1,
        current_revision=1,
        validator=None,
    )
    locator = _created_rect_locator(path, created["receipts"][0]["shape_id"])
    style = _style_textbox(path, locator, fill=fill, stroke=stroke)
    return {
        "box": created["receipts"][0],
        "locator": locator,
        "style": style,
        "bounds": [int(x), int(y), int(width), int(height)],
    }


def _execute_bar_chart(path, plan: dict, anchor: str) -> dict:
    receipts = []
    for row in plan["rows"]:
        bar = _insert_filled_rectangle(
            path,
            anchor,
            x=int(row["x"]),
            y=int(row["y"]),
            width=int(row["bar_width"]),
            height=int(row["bar_height"]),
            fill=plan["color"],
            stroke=plan["color"],
            z_order=1,
        )

        label = apply_drawing_layer_atomic(
            path,
            [{
                "op": "insert_textbox",
                "anchor": anchor,
                "paragraphs": [str(row["label"])],
                "width": max(2400, int(row["x"]) - 400),
                "height": int(row["bar_height"]) + 900,
                "horizontal_offset": int(row["label_x"]),
                "vertical_offset": int(row["y"]) - 250,
                "horz_rel_to": "PARA",
                "vert_rel_to": "PARA",
                "z_order": 2,
            }],
            expected_revision=1,
            current_revision=1,
            validator=None,
        )
        label_loc = _created_rect_locator(path, label["receipts"][0]["shape_id"])
        label_style = _style_textbox(path, label_loc)

        value_text = f"{row['value']:g}"
        value = apply_drawing_layer_atomic(
            path,
            [{
                "op": "insert_textbox",
                "anchor": anchor,
                "paragraphs": [value_text],
                "width": 5200,
                "height": int(row["bar_height"]) + 900,
                "horizontal_offset": int(row["value_x"]),
                "vertical_offset": int(row["y"]) - 250,
                "horz_rel_to": "PARA",
                "vert_rel_to": "PARA",
                "z_order": 2,
            }],
            expected_revision=1,
            current_revision=1,
            validator=None,
        )
        value_loc = _created_rect_locator(path, value["receipts"][0]["shape_id"])
        value_style = _style_textbox(path, value_loc)

        receipts.append({
            "semantic_group_id": f"{plan['component_id']}:bar:{row['index']}",
            "label": row["label"],
            "value": row["value"],
            "bar": bar,
            "label_box": label["receipts"][0],
            "label_style": label_style,
            "value_box": value["receipts"][0],
            "value_style": value_style,
            "children": ["shape", "label", "value"],
        })
    return {
        "component_id": plan["component_id"],
        "type": "bar_chart",
        "row_count": len(plan["rows"]),
        "receipts": receipts,
        "authority": "P4.9_GEOMETRY_SAFE_RECTANGLE_PLUS_TEXTBOX",
    }


def _execute_kpi_strip(path, plan: dict, anchor: str) -> dict:
    items = plan["items"]
    gap = 700
    width = int(plan["width"])
    height = int(plan["height"])
    box_width = max(4200, int((width - gap * (len(items) - 1)) / len(items)))
    receipts = []
    for item in items:
        x = int(item["index"]) * (box_width + gap)
        y = int(plan["top_offset"])
        background = _insert_filled_rectangle(
            path,
            anchor,
            x=x,
            y=y,
            width=box_width,
            height=height,
            fill="#F3F6FA",
            stroke="#AEB7C2",
            z_order=1,
        )

        inner_x = x + 500
        inner_width = max(1200, box_width - 1000)
        value_height = max(1800, min(2800, height // 2 - 300))
        label_height = max(1500, min(2400, height // 2 - 400))

        value = apply_drawing_layer_atomic(
            path,
            [{
                "op": "insert_textbox",
                "anchor": anchor,
                "paragraphs": [str(item["value"])],
                "width": inner_width,
                "height": value_height,
                "horizontal_offset": inner_x,
                "vertical_offset": y + 500,
                "horz_rel_to": "PARA",
                "vert_rel_to": "PARA",
                "z_order": 2,
            }],
            expected_revision=1,
            current_revision=1,
            validator=None,
        )
        value_loc = _created_rect_locator(path, value["receipts"][0]["shape_id"])
        value_style = _style_textbox(path, value_loc)

        label = apply_drawing_layer_atomic(
            path,
            [{
                "op": "insert_textbox",
                "anchor": anchor,
                "paragraphs": [str(item["label"])],
                "width": inner_width,
                "height": label_height,
                "horizontal_offset": inner_x,
                "vertical_offset": y + max(2600, height // 2),
                "horz_rel_to": "PARA",
                "vert_rel_to": "PARA",
                "z_order": 2,
            }],
            expected_revision=1,
            current_revision=1,
            validator=None,
        )
        label_loc = _created_rect_locator(path, label["receipts"][0]["shape_id"])
        label_style = _style_textbox(path, label_loc)

        receipts.append({
            "semantic_group_id": f"{plan['component_id']}:kpi:{item['index']}",
            "label": item["label"],
            "value": item["value"],
            "container": background,
            "value_box": value["receipts"][0],
            "value_style": value_style,
            "label_box": label["receipts"][0],
            "label_style": label_style,
            "children": ["container", "label", "value"],
        })
    return {
        "component_id": plan["component_id"],
        "type": "kpi_strip",
        "item_count": len(items),
        "receipts": receipts,
        "authority": "P4.9_BOUNDED_KPI_CARD_RECTANGLE_PLUS_SEPARATE_TEXTBOXES",
    }


def _execute_visual_plans(path, visual_plans: list[dict], bindings: dict[str, dict]) -> list[dict]:
    certificate = certify_visual_plans(visual_plans)
    if certificate["status"] != "PASS":
        raise ValueError(
            "P4.9 visual geometry certificate refused lowering: "
            + json.dumps(certificate["issues"], ensure_ascii=False, sort_keys=True)
        )
    receipts = []
    for plan in visual_plans:
        binding = bindings.get(str(plan["anchor_block_id"]))
        if not binding:
            raise ValueError(f"visual anchor block missing: {plan['anchor_block_id']}")
        anchor = str(binding["locator"])
        if plan["type"] == "bar_chart":
            receipts.append(_execute_bar_chart(path, plan, anchor))
        elif plan["type"] == "kpi_strip":
            receipts.append(_execute_kpi_strip(path, plan, anchor))
        else:
            raise ValueError(f"unsupported visual plan type: {plan['type']}")
    return receipts



def _compile_components_with_p49(spec: dict) -> dict:
    compiled = compile_document_components_kernel(spec)
    visual_certificate = certify_visual_plans(list(compiled.get("visual_plans") or []))
    compiled["p49_visual_certificate"] = visual_certificate
    if visual_certificate["status"] != "PASS":
        blockers = list(compiled.get("blockers") or [])
        for issue in visual_certificate["issues"]:
            blockers.append({
                "component_id": str(issue.get("component_id") or ""),
                "type": "visual_geometry",
                "reason": f"P49_{issue.get('code')}",
                "detail": issue.get("detail"),
                "evidence": issue,
                "repair_options": [
                    "increase_visual_dimensions",
                    "reduce_visual_item_count",
                    "use_data_table",
                ],
            })
        compiled["blockers"] = blockers
        compiled["ready"] = False
    return compiled


def _plan_component_repairs_with_p49(spec: dict) -> dict:
    base = plan_component_repairs_kernel(spec)
    compiled = _compile_components_with_p49(spec)
    repairs = list(base.get("repairs") or [])
    seen = {(str(item.get("component_id")), str(item.get("problem"))) for item in repairs}
    for blocker in compiled.get("blockers") or []:
        reason = str(blocker.get("reason") or "")
        if not reason.startswith("P49_"):
            continue
        key = (str(blocker.get("component_id") or ""), reason)
        if key in seen:
            continue
        seen.add(key)
        repairs.append({
            "component_id": key[0],
            "problem": reason,
            "detail": blocker.get("detail"),
            "safe_options": blocker.get("repair_options") or [],
            "automatic_mutation": False,
        })
    base["ready"] = compiled["ready"]
    base["repair_count"] = len(repairs)
    base["repairs"] = repairs
    base["repair_plan_sha256"] = hashlib.sha256(
        json.dumps(
            repairs,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    base["p49_visual_certificate"] = compiled["p49_visual_certificate"]
    return base

def register_p48_tools(core, refresh_metadata, delivery_after_commit):
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
    mutate = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)

    @core.mcp.tool(annotations=read)
    def get_component_authoring_contract() -> dict:
        core._caller_subject()
        return {"ok": True, **component_authoring_contract()}

    @core.mcp.tool(annotations=read)
    def compile_document_components(spec: dict) -> dict:
        core._caller_subject()
        return {"ok": True, **_compile_components_with_p49(spec)}

    @core.mcp.tool(annotations=read)
    def plan_component_repairs(spec: dict) -> dict:
        core._caller_subject()
        return {"ok": True, **_plan_component_repairs_with_p49(spec)}

    @core.mcp.tool(annotations=read)
    def get_p48_distribution_quickstart() -> dict:
        core._caller_subject()
        return {"ok": True, **distribution_quickstart_contract()}

    @core.mcp.tool(annotations=mutate)
    def create_component_document_and_deliver(
        spec: dict,
        filename: str = "document.hwpx",
        request_id: str = "",
        link_ttl_seconds: int = 900,
    ):
        owner_subject = core._caller_subject()
        core._download_secret()
        core._cleanup_expired()
        components = _compile_components_with_p49(spec)
        if not components["ready"]:
            raise ValueError(
                "P4.8 component plan blocked before mutation: "
                + json.dumps(components["blockers"], ensure_ascii=False, sort_keys=True)
            )

        unified_spec = dict(components["unified_spec"])
        supplied_native = spec.get("native_bundle")
        if supplied_native is not None:
            if not isinstance(supplied_native, dict):
                raise ValueError("spec.native_bundle must be an object")
            unified_spec["native_bundle"] = supplied_native
        compiled = compile_unified_authoring_plan_kernel(unified_spec)

        safe_filename = core.sanitize_filename(filename)
        normalized_request_id = str(request_id or "").strip()
        if len(normalized_request_id) > 160:
            raise ValueError("request_id exceeds 160 characters")
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "component_plan_sha256": components["component_plan_sha256"],
                    "unified_plan_sha256": compiled["unified_plan_sha256"],
                    "filename": safe_filename,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        durable_request = f"p48-components:{normalized_request_id}" if normalized_request_id else ""
        document_id = (
            core._idempotent_document_id(owner_subject, durable_request)
            if durable_request
            else core._new_document_id()
        )

        if durable_request:
            try:
                existing = core._load_metadata(document_id)
            except FileNotFoundError:
                existing = None
            if existing is not None:
                core._require_owner(existing)
                if existing.get("p48_component_request_sha256") != fingerprint:
                    raise RuntimeError("Idempotency conflict for P4.8 component authoring")
                return delivery_after_commit(
                    document_id,
                    int(existing.get("revision", 1)),
                    int(link_ttl_seconds),
                    "P48_COMPONENT_CREATE_VALIDATE_DELIVER",
                    extra={
                        "phase": "P4.8",
                        "product_context": {
                            "component_authoring": {
                                "component_plan_sha256": components["component_plan_sha256"],
                                "idempotent_replay": True,
                            }
                        },
                    },
                )

        path, _ = core._paths(document_id)
        try:
            composition = compose_document_plan(
                path,
                compiled["rich"]["plan"],
                validator=lambda candidate: core.validate_hwpx_package(candidate, ingress=False),
            )

            native_receipts = {}
            compiled_native = None
            if int(compiled["native_operation_count"]):
                mapped = build_document_map(path)
                compiled_native = compile_native_authoring_bundle(
                    compiled["native_bundle"],
                    document_map=mapped,
                )
                if not compiled_native["ready"]:
                    raise ValueError(
                        "P4.8 extra native bundle blocked: "
                        + json.dumps(compiled_native["blockers"], ensure_ascii=False, sort_keys=True)
                    )
                execution = compiled_native["execution_bundle"]
                if execution["equations"]:
                    native_receipts["equations"] = apply_equation_edits_atomic(
                        path, execution["equations"], expected_revision=1, current_revision=1, validator=None
                    )
                if execution["tables"]:
                    native_receipts["tables"] = apply_table_edits_atomic(
                        path, execution["tables"], expected_revision=1, current_revision=1, validator=None
                    )
                if execution["drawings"]:
                    native_receipts["drawings"] = apply_drawing_layer_atomic(
                        path, execution["drawings"], expected_revision=1, current_revision=1, validator=None
                    )

            visual_certificate = certify_visual_plans(list(components["visual_plans"]))
            if visual_certificate["status"] != "PASS":
                raise ValueError(
                    "P4.9 visual geometry certificate refused component mutation: "
                    + json.dumps(visual_certificate["issues"], ensure_ascii=False, sort_keys=True)
                )
            visual_receipts = _execute_visual_plans(
                path,
                list(components["visual_plans"]),
                dict(composition["bindings"]),
            )
            materialized_visual_audit = audit_materialized_visuals(path, visual_receipts)
            if materialized_visual_audit["status"] != "PASS":
                raise ValueError(
                    "P4.9 post-materialization visual audit refused delivery: "
                    + json.dumps(materialized_visual_audit["issues"], ensure_ascii=False, sort_keys=True)
                )

            validation = core.validate_hwpx_package(path, ingress=False)
            readiness = evaluate_preview_readiness(
                path,
                mode="POLISHED_REPORT",
                validator=lambda candidate: core.validate_hwpx_package(candidate, ingress=False),
            )
            if readiness["verdict"] in {"FAIL", "HOLD"}:
                raise ValueError(
                    f"P4.8 preview-readiness gate refused delivery: {readiness['verdict']}"
                )

            logical = compiled["rich"]["plan"].get("document") or {}
            metadata = core._metadata(
                document_id,
                filename=safe_filename,
                owner_subject=owner_subject,
                validation=validation,
                title=str(logical.get("title") or "") if isinstance(logical, dict) else "",
                source="p48-component-authoring",
            )
            metadata["p48_component_request_sha256"] = fingerprint
            metadata["p48_component_plan_sha256"] = components["component_plan_sha256"]
            metadata["p48_unified_plan_sha256"] = compiled["unified_plan_sha256"]
            metadata["p48_component_count"] = int(components["component_count"])
            metadata["p48_archetype"] = components["archetype"]
            metadata["p48_visual_component_count"] = len(visual_receipts)
            metadata["p48_visual_receipts"] = visual_receipts
            metadata["p49_visual_certificate_status"] = visual_certificate["status"]
            metadata["p49_visual_certificate_sha256"] = visual_certificate["visual_certificate_sha256"]
            metadata["p49_materialized_visual_audit_status"] = materialized_visual_audit["status"]
            metadata["p49_materialized_visual_audit_sha256"] = materialized_visual_audit["materialized_visual_audit_sha256"]
            metadata["p48_native_bundle_sha256"] = None if compiled_native is None else compiled_native["bundle_sha256"]
            metadata["p48_preview_readiness_sha256"] = readiness["preview_readiness_sha256"]
            if normalized_request_id:
                metadata["create_request_id_sha256"] = hashlib.sha256(
                    normalized_request_id.encode("utf-8")
                ).hexdigest()

            doc_map = build_document_map(path)
            fmt_map = build_formatting_map(path)
            inline_map = build_inline_map(path)
            table_map = build_table_map(path)
            object_map = build_object_map(path)
            equation_map = build_equation_map(path)
            drawing_map = build_drawing_layer_map(path)
            style_map = build_drawing_style_map(path)
            metadata["p48_drawing_structure_sha256"] = drawing_map["drawing_structure_sha256"]
            metadata["p48_drawing_style_sha256"] = style_map["drawing_style_sha256"]
            refresh_metadata(
                document_id,
                metadata,
                validation,
                doc_map,
                fmt_map,
                inline_map,
                table_map,
                object_map,
                equation_map,
            )
        except Exception:
            core._delete_document_files(document_id)
            raise

        return delivery_after_commit(
            document_id,
            1,
            int(link_ttl_seconds),
            "P48_COMPONENT_CREATE_VALIDATE_DELIVER",
            extra={
                "phase": "P4.8",
                "product_context": {
                    "component_authoring": {
                        "component_plan_sha256": components["component_plan_sha256"],
                        "component_count": components["component_count"],
                        "archetype": components["archetype"],
                        "visual_component_count": len(visual_receipts),
                        "visual_receipts": visual_receipts,
                        "p49_visual_certificate": {
                            "status": visual_certificate["status"],
                            "sha256": visual_certificate["visual_certificate_sha256"],
                        },
                        "p49_materialized_visual_audit": {
                            "status": materialized_visual_audit["status"],
                            "sha256": materialized_visual_audit["materialized_visual_audit_sha256"],
                        },
                        "native_receipts": native_receipts,
                        "preview_readiness": readiness,
                        "idempotent_replay": False,
                        "revision_semantics": "PRIVATE_COMPONENT_CANDIDATE_TO_SINGLE_REVISION_1_COMMIT",
                    }
                },
            },
        )

    return {
        "phase": "P4.8",
        "product": "0.34.0-p4.8",
        "authority": "SEMANTIC_COMPONENT_AUTHORING_AND_STRUCTURAL_NATIVE_VISUALS",
    }
