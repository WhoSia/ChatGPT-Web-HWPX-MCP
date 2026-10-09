from __future__ import annotations

import tempfile
from pathlib import Path
from mcp.types import ToolAnnotations

from hwpx_mcp.operations.p41_operational import (
    DEFAULT_MIGRATION_CANDIDATE,
    diagnose_failure,
    evaluate_upgrade_candidate,
    operational_readiness_contract,
    profile_operations,
    runtime_compatibility_matrix,
)

def register_p41_tools(core):
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)

    @core.mcp.tool(annotations=read)
    def get_product_operational_readiness_contract() -> dict:
        core._caller_subject()
        return {"ok": True, **operational_readiness_contract()}

    @core.mcp.tool(annotations=read)
    def get_product_runtime_compatibility(candidate_python_hwpx_version: str = DEFAULT_MIGRATION_CANDIDATE) -> dict:
        core._caller_subject()
        return {"ok": True, **runtime_compatibility_matrix(candidate_python_hwpx_version)}

    @core.mcp.tool(annotations=read)
    def profile_product_operational_baseline(sample_count: int = 3) -> dict:
        core._caller_subject()
        holder = tempfile.TemporaryDirectory()
        root = Path(holder.name)
        baseline_path = root / "baseline.hwpx"
        core.materialize_hwpx(baseline_path, "P4.1 operational baseline\n두 번째 문단", "P4.1")
        def create_validate():
            target = root / "candidate.hwpx"
            core.materialize_hwpx(target, "P4.1 operational baseline\n두 번째 문단", "P4.1")
            core.validate_hwpx_package(target, ingress=True)
        def validate_existing():
            core.validate_hwpx_package(baseline_path, ingress=True)
        try:
            result = profile_operations(
                {
                    "minimal_hwpx_create_validate": (create_validate, 5000.0),
                    "existing_hwpx_validate": (validate_existing, 3000.0),
                },
                sample_count=int(sample_count),
            )
        finally:
            holder.cleanup()
        return {"ok": result["status"] == "PASS", **result}

    @core.mcp.tool(annotations=read)
    def diagnose_product_failure(message: str = "", code: str = "") -> dict:
        core._caller_subject()
        return {"ok": True, **diagnose_failure(message=message, code=code)}

    @core.mcp.tool(annotations=read)
    def evaluate_python_hwpx_upgrade(candidate_version: str, evidence: dict) -> dict:
        core._caller_subject()
        result = evaluate_upgrade_candidate(candidate_version, evidence)
        return {"ok": result["verdict"] == "READY_FOR_CONTROLLED_CANARY", **result}

    return {"phase": "P4.1", "authority": "PRODUCT_OPERATIONAL_READINESS_AND_MIGRATION_EVIDENCE"}
