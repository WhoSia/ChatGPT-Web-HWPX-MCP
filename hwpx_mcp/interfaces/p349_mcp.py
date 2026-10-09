from __future__ import annotations
from typing import Any,Callable
from mcp.types import ToolAnnotations
from hwpx_mcp.extensions.p349_composition import CompositionRegistry,composition_contract
def register_p349_tools(core,owned_document:Callable[[str],tuple[dict,Any]],p347_registry,adapter_registry):
    read=ToolAnnotations(readOnlyHint=True,destructiveHint=False,openWorldHint=False);mutate=ToolAnnotations(readOnlyHint=False,destructiveHint=True,openWorldHint=False);registry=CompositionRegistry(p347_registry,adapter_registry)
    def own(document_id:str):owned_document(document_id)
    @core.mcp.tool(annotations=read)
    def get_extension_composition_contract()->dict:core._caller_subject();return {"ok":True,**composition_contract()}
    @core.mcp.tool(annotations=read)
    def analyze_extension_composition(document_id:str,package_ids:list[str],serial_order:list[str],max_effect:str="DELIVERY")->dict:
        own(document_id);out=registry.analyze(document_id,package_ids,serial_order,max_effect);return {"ok":out.get("status")=="PASS",**out}
    @core.mcp.tool(annotations=mutate)
    def certify_extension_composition(document_id:str,package_ids:list[str],serial_order:list[str],joint_host_observations:list[dict],expected_registry_generation:int,max_effect:str="DELIVERY")->dict:
        own(document_id);out=registry.certify(document_id,package_ids,serial_order,joint_host_observations,int(expected_registry_generation),max_effect);return {"ok":out.get("status")=="PASS",**out}
    @core.mcp.tool(annotations=read)
    def get_extension_composition_state(document_id:str)->dict:own(document_id);return {"ok":True,**registry.snapshot(document_id)}
    @core.mcp.tool(annotations=mutate)
    def activate_extension_composition(document_id:str,composition_id:str,expected_composition_generation:int,expected_registry_generation:int)->dict:
        own(document_id);return {"ok":True,**registry.activate(document_id,composition_id,int(expected_composition_generation),int(expected_registry_generation))}
    @core.mcp.tool(annotations=mutate)
    def rollback_extension_composition(document_id:str,expected_composition_generation:int)->dict:
        own(document_id);return {"ok":True,**registry.rollback(document_id,int(expected_composition_generation))}
    return registry
