from __future__ import annotations

import os
import tempfile
from pathlib import Path

from mcp.types import ToolAnnotations

from hwpx_mcp.document.p2_document import build_document_map
from hwpx_mcp.document.p22_formatting import build_formatting_map
from hwpx_mcp.document.p24_inline import build_inline_map
from hwpx_mcp.document.p28_tables import apply_table_edits_atomic, build_table_map
from hwpx_mcp.document.p29_objects import build_object_map
from hwpx_mcp.document.p210_equations import apply_equation_edits_atomic, build_equation_map
from hwpx_mcp.document.p325_drawing_layer import apply_drawing_layer_atomic, build_drawing_layer_map
from hwpx_mcp.rendering.p46_native_authoring import (
    compile_native_authoring_bundle as compile_native_authoring_bundle_kernel,
    equation_capability_matrix,
    native_authoring_contract,
    real_document_benchmark_contract,
)


def register_p46_tools(core, owned_document, refresh_metadata):
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
    mutate = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)

    @core.mcp.tool(annotations=read)
    def get_native_authoring_contract() -> dict:
        core._caller_subject()
        return {"ok": True, **native_authoring_contract()}

    @core.mcp.tool(annotations=read)
    def inspect_native_authoring_capabilities(latex_samples: list[str] | None = None) -> dict:
        core._caller_subject()
        return {"ok": True, "equations": equation_capability_matrix(latex_samples)}

    @core.mcp.tool(annotations=read)
    def compile_native_authoring_bundle(document_id: str, bundle: dict) -> dict:
        metadata, path = owned_document(document_id)
        mapped = build_document_map(path)
        return {
            "ok": True,
            "document_id": document_id,
            "revision": int(metadata["revision"]),
            **compile_native_authoring_bundle_kernel(bundle, document_map=mapped),
        }

    @core.mcp.tool(annotations=mutate)
    def apply_native_authoring_bundle(
        document_id: str,
        expected_revision: int,
        bundle: dict,
        lease_token: str = "",
    ) -> dict:
        metadata, path = owned_document(document_id)
        current = int(metadata["revision"])
        if int(expected_revision) != current:
            raise ValueError(f"Stale revision: expected {expected_revision}, current {current}")

        mapped = build_document_map(path)
        compiled = compile_native_authoring_bundle_kernel(bundle, document_map=mapped)
        if not compiled["ready"]:
            raise ValueError(f"P4.6 native authoring bundle blocked: {compiled['blockers']}")

        fd, tmp_name = tempfile.mkstemp(
            prefix=path.stem + ".p46-authoring-",
            suffix=".hwpx",
            dir=str(path.parent),
        )
        os.close(fd)
        candidate = Path(tmp_name)
        candidate.write_bytes(path.read_bytes())
        lane_receipts: dict[str, dict] = {}
        ingress = metadata.get("source") == "existing-ingress"

        try:
            execution = compiled["execution_bundle"]
            if execution["equations"]:
                lane_receipts["equations"] = apply_equation_edits_atomic(
                    candidate,
                    execution["equations"],
                    expected_revision=current,
                    current_revision=current,
                    validator=None,
                )
            if execution["tables"]:
                lane_receipts["tables"] = apply_table_edits_atomic(
                    candidate,
                    execution["tables"],
                    expected_revision=current,
                    current_revision=current,
                    validator=None,
                )
            if execution["drawings"]:
                lane_receipts["drawings"] = apply_drawing_layer_atomic(
                    candidate,
                    execution["drawings"],
                    expected_revision=current,
                    current_revision=current,
                    validator=None,
                )

            validation = core.validate_hwpx_package(candidate, ingress=ingress)
            after_document = build_document_map(candidate)
            after_formatting = build_formatting_map(candidate)
            after_inline = build_inline_map(candidate)
            after_tables = build_table_map(candidate)
            after_objects = build_object_map(candidate)
            after_equations = build_equation_map(candidate)
            after_drawings = build_drawing_layer_map(candidate)

            os.replace(candidate, path)
            metadata["revision"] = current + 1
            metadata["last_edit_at"] = core._utc_iso()
            metadata["p46_bundle_sha256"] = compiled["bundle_sha256"]
            metadata["p46_drawing_structure_sha256"] = after_drawings["drawing_structure_sha256"]
            metadata["p46_drawing_geometry_sha256"] = after_drawings["drawing_geometry_sha256"]
            if lease_token:
                metadata["_commit_lease_token"] = lease_token
            refresh_metadata(
                document_id,
                metadata,
                validation,
                after_document,
                after_formatting,
                after_inline,
                after_tables,
                after_objects,
                after_equations,
            )
        except Exception:
            try:
                candidate.unlink()
            except FileNotFoundError:
                pass
            raise

        return {
            "ok": True,
            "document_id": document_id,
            "revision_before": current,
            "revision_after": int(metadata["revision"]),
            "sha256": validation["sha256"],
            "bundle_sha256": compiled["bundle_sha256"],
            "lane_counts": compiled["lane_counts"],
            "lane_receipts": lane_receipts,
            "validation": validation,
            "transaction": "COMMITTED",
            "authority": "P4.6_ONE_CALL_ONE_DURABLE_REVISION",
        }

    @core.mcp.tool(annotations=read)
    def get_real_document_generation_benchmark() -> dict:
        core._caller_subject()
        return {"ok": True, **real_document_benchmark_contract()}

    return {"phase": "P4.6", "authority": "NATIVE_AUTHORING_FIDELITY_AND_ERGONOMICS"}
