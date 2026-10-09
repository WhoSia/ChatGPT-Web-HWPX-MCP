from __future__ import annotations
from mcp.types import ToolAnnotations
from p43_quality import (
    adjudicate_release_health,build_failure_bundle,load_release_history,
    localize_regression,quality_service_contract,
)

def register_p43_tools(core):
    read=ToolAnnotations(readOnlyHint=True,destructiveHint=False,openWorldHint=False)

    @core.mcp.tool(annotations=read)
    def get_continuous_product_health_contract()->dict:
        core._caller_subject()
        return {"ok":True,**quality_service_contract()}

    @core.mcp.tool(annotations=read)
    def get_cross_release_benchmark_history()->dict:
        core._caller_subject()
        return {"ok":True,**load_release_history()}

    @core.mcp.tool(annotations=read)
    def localize_product_regression(observation:dict)->dict:
        core._caller_subject()
        return {"ok":True,**localize_regression(observation)}

    @core.mcp.tool(annotations=read)
    def build_reproducible_failure_bundle(context:dict)->dict:
        core._caller_subject()
        return {"ok":True,**build_failure_bundle(context)}

    @core.mcp.tool(annotations=read)
    def adjudicate_continuous_product_health(receipt:dict)->dict:
        core._caller_subject()
        result=adjudicate_release_health(receipt)
        return {"ok":result["verdict"]=="PASS",**result}

    return {"phase":"P4.3","authority":"CONTINUOUS_PRODUCT_HEALTH_AND_REGRESSION_LOCALIZATION"}
