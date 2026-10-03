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
from p325_drawing_layer import apply_drawing_layer_atomic, build_drawing_layer_map
from p338_rich_builder import evaluate_preview_readiness
from p321_document_composer import compose_document_plan
from p46_native_authoring import compile_native_authoring_bundle
from p416_generation_manifest import build_authoring_generation_manifest
from p47_native_authoring import (
    adjudicate_equation_render_evidence as adjudicate_equation_render_evidence_kernel,
    authoring_v2_contract,
    compile_unified_authoring_plan as compile_unified_authoring_plan_kernel,
    equation_render_frontier,
)


def register_p47_tools(core, refresh_metadata, delivery_after_commit):
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
    mutate = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)

    @core.mcp.tool(annotations=read)
    def get_authoring_v2_contract() -> dict:
        core._caller_subject()
        return {"ok": True, **authoring_v2_contract()}

    @core.mcp.tool(annotations=read)
    def inspect_equation_render_frontier() -> dict:
        core._caller_subject()
        return {"ok": True, **equation_render_frontier()}

    @core.mcp.tool(annotations=read)
    def adjudicate_equation_render_evidence(receipt: dict | None = None) -> dict:
        core._caller_subject()
        return {"ok": True, **adjudicate_equation_render_evidence_kernel(receipt)}

    @core.mcp.tool(annotations=read)
    def compile_unified_authoring_plan(spec: dict) -> dict:
        core._caller_subject()
        return {"ok": True, **compile_unified_authoring_plan_kernel(spec)}

    @core.mcp.tool(annotations=mutate)
    def create_unified_document_and_deliver(
        spec: dict,
        filename: str = "document.hwpx",
        request_id: str = "",
        link_ttl_seconds: int = 900,
    ):
        owner_subject = core._caller_subject()
        core._download_secret()
        core._cleanup_expired()
        compiled = compile_unified_authoring_plan_kernel(spec)
        safe_filename = core.sanitize_filename(filename)
        normalized_request_id = str(request_id or "").strip()
        if len(normalized_request_id) > 160:
            raise ValueError("request_id exceeds 160 characters")
        fingerprint = hashlib.sha256(
            json.dumps(
                {"unified_plan_sha256": compiled["unified_plan_sha256"], "filename": safe_filename},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        durable_request = f"p47-unified:{normalized_request_id}" if normalized_request_id else ""
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
                if existing.get("p47_unified_request_sha256") != fingerprint:
                    raise RuntimeError("Idempotency conflict for P4.7 unified authoring")
                return delivery_after_commit(
                    document_id,
                    int(existing.get("revision", 1)),
                    int(link_ttl_seconds),
                    "P47_UNIFIED_CREATE_VALIDATE_DELIVER",
                    extra={
                        "phase": "P4.7",
                        "product_context": {
                            "unified_authoring": {
                                "unified_plan_sha256": compiled["unified_plan_sha256"],
                                "idempotent_replay": True,
                                "generation_manifest": existing.get("p416_generation_manifest"),
                                "generation_manifest_sha256": existing.get("p416_generation_manifest_sha256"),
                            }
                        },
                    },
                )

        path, _ = core._paths(document_id)
        try:
            compose_document_plan(
                path,
                compiled["rich"]["plan"],
                validator=lambda candidate: core.validate_hwpx_package(candidate, ingress=False),
            )
            lane_receipts = {}
            native_bundle = compiled["native_bundle"]
            native_count = int(compiled["native_operation_count"])
            compiled_native = None
            if native_count:
                mapped = build_document_map(path)
                compiled_native = compile_native_authoring_bundle(native_bundle, document_map=mapped)
                if not compiled_native["ready"]:
                    raise ValueError(f"P4.7 unified native bundle blocked: {compiled_native['blockers']}")
                execution = compiled_native["execution_bundle"]
                if execution["equations"]:
                    lane_receipts["equations"] = apply_equation_edits_atomic(
                        path, execution["equations"], expected_revision=1, current_revision=1, validator=None
                    )
                if execution["tables"]:
                    lane_receipts["tables"] = apply_table_edits_atomic(
                        path, execution["tables"], expected_revision=1, current_revision=1, validator=None
                    )
                if execution["drawings"]:
                    lane_receipts["drawings"] = apply_drawing_layer_atomic(
                        path, execution["drawings"], expected_revision=1, current_revision=1, validator=None
                    )

            validation = core.validate_hwpx_package(path, ingress=False)
            readiness = evaluate_preview_readiness(
                path,
                mode="POLISHED_REPORT",
                validator=lambda candidate: core.validate_hwpx_package(candidate, ingress=False),
            )
            if readiness["verdict"] in {"FAIL", "HOLD"}:
                raise ValueError(f"P4.7 preview-readiness gate refused delivery: {readiness['verdict']}")

            tool_trace = [
                {"tool": "compose_document_plan", "capability": "RICH_COMPOSITION", "operation": {"unified_plan_sha256": compiled["unified_plan_sha256"]}},
                {"tool": "validate_hwpx_package", "capability": "PACKAGE_VALIDATION", "operation": {"validation_sha256": validation["sha256"]}},
                {"tool": "evaluate_preview_readiness", "capability": "PREVIEW_READINESS", "operation": {"preview_readiness_sha256": readiness["preview_readiness_sha256"]}},
            ]
            capability_path = ["P4.7_UNIFIED_AUTHORING", "RICH_COMPOSITION"]
            if compiled_native is not None:
                capability_path.append("NATIVE_AUTHORING_BUNDLE")
                execution = compiled_native["execution_bundle"]
                if execution["equations"]:
                    tool_trace.append({"tool": "apply_equation_edits_atomic", "capability": "NATIVE_EQUATION", "operation": {"count": len(execution["equations"])}})
                if execution["tables"]:
                    tool_trace.append({"tool": "apply_table_edits_atomic", "capability": "NATIVE_TABLE", "operation": {"count": len(execution["tables"])}})
                if execution["drawings"]:
                    tool_trace.append({"tool": "apply_drawing_layer_atomic", "capability": "NATIVE_DRAWING", "operation": {"count": len(execution["drawings"])}})
            generation_manifest = build_authoring_generation_manifest(
                path,
                intent=spec,
                plan={
                    "unified_plan_sha256": compiled["unified_plan_sha256"],
                    "rich_compile_sha256": compiled["rich"]["compile_sha256"],
                    "native_bundle_sha256": None if compiled_native is None else compiled_native["bundle_sha256"],
                },
                capability_path=capability_path,
                tool_trace=tool_trace,
                deterministic_parameters={
                    "filename": safe_filename,
                    "native_operation_count": int(compiled["native_operation_count"]),
                    "revision_semantics": "PRIVATE_CANDIDATE_TO_SINGLE_REVISION_1_COMMIT",
                },
            )

            logical = compiled["rich"]["plan"].get("document") or {}
            metadata = core._metadata(
                document_id,
                filename=safe_filename,
                owner_subject=owner_subject,
                validation=validation,
                title=str(logical.get("title") or "") if isinstance(logical, dict) else "",
                source="p47-unified-authoring",
            )
            metadata["p47_unified_request_sha256"] = fingerprint
            metadata["p47_unified_plan_sha256"] = compiled["unified_plan_sha256"]
            metadata["p47_rich_compile_sha256"] = compiled["rich"]["compile_sha256"]
            metadata["p47_native_bundle_sha256"] = None if compiled_native is None else compiled_native["bundle_sha256"]
            metadata["p47_preview_readiness_sha256"] = readiness["preview_readiness_sha256"]
            metadata["p47_lane_receipts"] = lane_receipts
            metadata["p416_generation_manifest"] = generation_manifest
            metadata["p416_generation_manifest_sha256"] = generation_manifest["manifest_sha256"]
            if normalized_request_id:
                metadata["create_request_id_sha256"] = hashlib.sha256(normalized_request_id.encode("utf-8")).hexdigest()

            doc_map = build_document_map(path)
            fmt_map = build_formatting_map(path)
            inline_map = build_inline_map(path)
            table_map = build_table_map(path)
            object_map = build_object_map(path)
            equation_map = build_equation_map(path)
            drawing_map = build_drawing_layer_map(path)
            metadata["p47_drawing_structure_sha256"] = drawing_map["drawing_structure_sha256"]
            metadata["p47_drawing_geometry_sha256"] = drawing_map["drawing_geometry_sha256"]
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
            "P47_UNIFIED_CREATE_VALIDATE_DELIVER",
            extra={
                "phase": "P4.7",
                "product_context": {
                    "unified_authoring": {
                        "unified_plan_sha256": compiled["unified_plan_sha256"],
                        "native_operation_count": compiled["native_operation_count"],
                        "lane_receipts": lane_receipts,
                        "preview_readiness": readiness,
                        "idempotent_replay": False,
                        "revision_semantics": "PRIVATE_CANDIDATE_TO_SINGLE_REVISION_1_COMMIT",
                        "generation_manifest": generation_manifest,
                        "generation_manifest_sha256": generation_manifest["manifest_sha256"],
                    }
                },
            },
        )

    return {"phase": "P4.7", "authority": "RENDER_GROUNDED_UNIFIED_AUTHORING"}
