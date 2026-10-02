from __future__ import annotations

from mcp.types import ToolAnnotations

from p412_native_repair import (
    causal_localization,
    compile_repaired_visual_payload,
    defect_eradication_contract,
    evaluate_blocking_promotion,
    requalify_golden_corpus,
)

def register_p412_tools(core):
    read=ToolAnnotations(readOnlyHint=True,destructiveHint=False,openWorldHint=False)

    @core.mcp.tool(annotations=read)
    def get_p412_defect_eradication_contract() -> dict:
        core._caller_subject()
        return {"ok":True,**defect_eradication_contract()}

    @core.mcp.tool(annotations=read)
    def localize_p412_native_visual_failure(component_type: str) -> dict:
        core._caller_subject()
        return {"ok":True,**causal_localization(component_type)}

    @core.mcp.tool(annotations=read)
    def compile_p412_repaired_visual_payload(plan: dict) -> dict:
        core._caller_subject()
        return {"ok":True,**compile_repaired_visual_payload(plan)}

    @core.mcp.tool(annotations=read)
    def requalify_p412_golden_corpus(native_observations: list[dict]) -> dict:
        core._caller_subject()
        return {"ok":True,**requalify_golden_corpus(native_observations)}

    @core.mcp.tool(annotations=read)
    def evaluate_p412_blocking_promotion(evidence: dict) -> dict:
        core._caller_subject()
        return {"ok":True,**evaluate_blocking_promotion(evidence)}

    return {
        "phase":"P4.12",
        "product":"0.37.0-p4.12",
        "authority":"NATIVE_VISUAL_DEFECT_ERADICATION_AND_BLOCKING_PROMOTION_COURT",
    }
