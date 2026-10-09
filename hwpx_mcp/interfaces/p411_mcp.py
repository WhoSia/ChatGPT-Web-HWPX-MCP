from __future__ import annotations

from mcp.types import ToolAnnotations

from hwpx_mcp.custody.p411_capture_protocol import capture_worker_contract, validate_capture_request, validate_capture_receipt
from hwpx_mcp.evidence.p411_release_service import evaluate_release_candidate, release_promotion_contract
from p411_visual_oracle import (
    adjudicate_repair_candidate,
    build_golden_registry,
    calibration_summary,
    detect_native_visual_defects,
    evaluate_shadow_release_gate,
    evaluate_visual_slo,
    load_calibration,
    load_native_raster_calibration,
    load_visual_slo_policy,
    native_render_oracle_contract,
    plan_bounded_repairs,
)

def register_p411_tools(core):
    read=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)

    @core.mcp.tool(annotations=read)
    def get_p411_native_render_oracle_contract() -> dict:
        core._caller_subject()
        return {"ok":True, **native_render_oracle_contract()}

    @core.mcp.tool(annotations=read)
    def get_p411_golden_registry() -> dict:
        core._caller_subject()
        return {"ok":True, **build_golden_registry(load_calibration())}

    @core.mcp.tool(annotations=read)
    def get_p411_calibration_summary() -> dict:
        core._caller_subject()
        return {"ok":True, **calibration_summary()}

    @core.mcp.tool(annotations=read)
    def get_p411_native_raster_calibration() -> dict:
        core._caller_subject()
        return {"ok":True, **load_native_raster_calibration()}

    @core.mcp.tool(annotations=read)
    def get_p411_visual_slo_policy() -> dict:
        core._caller_subject()
        return {"ok":True, **load_visual_slo_policy()}

    @core.mcp.tool(annotations=read)
    def evaluate_p411_native_visual_observation(observation: dict) -> dict:
        core._caller_subject()
        defects=detect_native_visual_defects(observation)
        slo=evaluate_visual_slo(defects, novel_unadjudicated=int(observation.get("novel_unadjudicated") or 0))
        repairs=plan_bounded_repairs(defects)
        return {"ok":True, "defects":defects, "visual_slo":slo, "repair_plan":repairs}

    @core.mcp.tool(annotations=read)
    def adjudicate_p411_visual_repair_candidate(evidence: dict) -> dict:
        core._caller_subject()
        result=adjudicate_repair_candidate(
            before=evidence.get("before") or {},
            after=evidence.get("after") or {},
            semantic_equivalence_pass=bool(evidence.get("semantic_equivalence_pass")),
            structural_proof_pass=bool(evidence.get("structural_proof_pass")),
            native_rerender_pass=bool(evidence.get("native_rerender_pass")),
        )
        return {"ok":True, **result}

    @core.mcp.tool(annotations=read)
    def evaluate_p411_shadow_release_gate(evidence: dict) -> dict:
        core._caller_subject()
        defects=detect_native_visual_defects(evidence.get("observation") or {})
        slo=evaluate_visual_slo(defects, novel_unadjudicated=int(evidence.get("novel_unadjudicated") or 0))
        gate=evaluate_shadow_release_gate(
            static_test_pass=bool(evidence.get("static_test_pass")),
            structural_fidelity_pass=bool(evidence.get("structural_fidelity_pass")),
            exact_head_docker_pass=bool(evidence.get("exact_head_docker_pass")),
            native_capture_pass=bool(evidence.get("native_capture_pass")),
            visual_slo=slo,
            novel_unadjudicated=int(evidence.get("novel_unadjudicated") or 0),
            blocking=False,
        )
        return {"ok":True, "visual_slo":slo, "gate":gate}

    @core.mcp.tool(annotations=read)
    def get_p411_release_promotion_contract() -> dict:
        core._caller_subject()
        return {"ok":True, **release_promotion_contract()}

    @core.mcp.tool(annotations=read)
    def evaluate_p411_release_candidate(evidence: dict, mode: str = "SHADOW_NONBLOCKING") -> dict:
        core._caller_subject()
        return {"ok":True, **evaluate_release_candidate(evidence, mode=mode)}

    @core.mcp.tool(annotations=read)
    def get_p411_windows_capture_worker_contract() -> dict:
        core._caller_subject()
        return {"ok":True, **capture_worker_contract()}

    @core.mcp.tool(annotations=read)
    def validate_p411_capture_request(request: dict) -> dict:
        core._caller_subject()
        return {"ok":True, **validate_capture_request(request)}

    @core.mcp.tool(annotations=read)
    def validate_p411_capture_receipt(receipt: dict) -> dict:
        core._caller_subject()
        return {"ok":True, **validate_capture_receipt(receipt)}

    return {
        "phase":"P4.11",
        "product":"0.36.0-p4.11",
        "authority":"CONTINUOUS_NATIVE_RENDER_ORACLE_AND_SHADOW_RELEASE_GATE",
    }
