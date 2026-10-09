from __future__ import annotations

from typing import Any,Callable,Mapping
from mcp.types import ToolAnnotations

from hwpx_mcp.extensions.p347_supply_chain_bridge import normalize_extension_package
from p348_marketplace import (
    marketplace_contract,verify_snapshot,discover_candidates,compare_snapshots,verify_offline_bundle,
)


def register_p348_tools(core,owned_document:Callable[[str],tuple[dict,Any]],p347_registry):
    read_only=ToolAnnotations(readOnlyHint=True,destructiveHint=False,openWorldHint=False)
    mutate=ToolAnnotations(readOnlyHint=False,destructiveHint=True,openWorldHint=False)

    @core.mcp.tool(annotations=read_only)
    def get_extension_marketplace_contract()->dict:
        core._caller_subject()
        return {"ok":True,**marketplace_contract()}

    @core.mcp.tool(annotations=read_only)
    def verify_extension_marketplace_snapshot(snapshot:dict,trust_policy:dict)->dict:
        core._caller_subject()
        result=verify_snapshot(snapshot,trust_policy)
        return {"ok":True,**result}

    @core.mcp.tool(annotations=read_only)
    def discover_extension_marketplace(snapshot:dict,trust_policy:dict,request:dict|None=None)->dict:
        core._caller_subject()
        verified=verify_snapshot(snapshot,trust_policy)
        result=discover_candidates(verified["state"],request or {})
        return {"ok":True,"snapshot_sha256":verified["snapshot_sha256"],**result}

    @core.mcp.tool(annotations=read_only)
    def compare_extension_marketplace_mirrors(left_snapshot:dict,right_snapshot:dict,trust_policy:dict)->dict:
        core._caller_subject()
        result=compare_snapshots(left_snapshot,right_snapshot,trust_policy)
        return {"ok":result["verdict"] in {"IDENTICAL","CONSISTENT_PREFIX"},**result}

    @core.mcp.tool(annotations=read_only)
    def verify_extension_marketplace_bundle(bundle:dict,trust_policy:dict)->dict:
        core._caller_subject()
        result=verify_offline_bundle(bundle,trust_policy)
        return {"ok":True,**result}

    @core.mcp.tool(annotations=mutate)
    def install_marketplace_extension(
        document_id:str,bundle:dict,trust_policy:dict,package:dict,rebuild_package:dict,
        host_observations:list[dict],expected_generation:int,dependency_catalog:list[dict]|None=None,
    )->dict:
        owned_document(document_id)
        verified=verify_offline_bundle(bundle,trust_policy)
        normalized=normalize_extension_package(package)
        if normalized["package_id"]!=verified["package_id"]:
            raise RuntimeError("P3.48 marketplace bundle/package content-address mismatch")
        installed=p347_registry.install(
            package,rebuild_package=rebuild_package,host_observations=host_observations,
            dependency_catalog=dependency_catalog or [],document_id=document_id,
            expected_generation=int(expected_generation),
        )
        return {
            "ok":True,
            "marketplace_snapshot_sha256":verified["snapshot_sha256"],
            "marketplace_authority":"DISCOVERY_AND_DISTRIBUTION_ONLY",
            **installed,
            "authority":"MARKETPLACE_VERIFIED_P347_INSTALL_TIME_RECERTIFICATION_PASS",
        }

    @core.mcp.tool(annotations=mutate)
    def reconcile_revoked_marketplace_extension(
        document_id:str,snapshot:dict,trust_policy:dict,extension_id:str,expected_generation:int,
    )->dict:
        owned_document(document_id)
        verified=verify_snapshot(snapshot,trust_policy)
        state=verified["state"]
        local=p347_registry.snapshot(document_id)
        promoted=(local.get("promoted_by_extension") or {}).get(extension_id)
        if not promoted:
            return {"ok":True,"action":"NONE","reason":"NO_PROMOTED_PACKAGE","snapshot_sha256":verified["snapshot_sha256"]}
        row=next((x for x in state.get("packages",[]) if x.get("package_id")==promoted),None)
        if row is None or row.get("state")!="REVOKED":
            return {"ok":True,"action":"NONE","reason":"PROMOTED_PACKAGE_NOT_REVOKED","package_id":promoted,"snapshot_sha256":verified["snapshot_sha256"]}
        try:
            result=p347_registry.rollback(extension_id,document_id=document_id,expected_generation=int(expected_generation))
            return {"ok":True,"action":"ROLLBACK","revoked_package_id":promoted,"snapshot_sha256":verified["snapshot_sha256"],**result,"authority":"REVOKED_PACKAGE_EXACT_CERTIFIED_ROLLBACK_PASS"}
        except RuntimeError as exc:
            if "no prior promoted package" not in str(exc):
                raise
            result=p347_registry.advance(promoted,"RETIRED",document_id=document_id,expected_generation=int(expected_generation))
            return {"ok":True,"action":"RETIRE","revoked_package_id":promoted,"snapshot_sha256":verified["snapshot_sha256"],**result,"authority":"REVOKED_PACKAGE_RETIRED_NO_SAFE_ROLLBACK_TARGET"}

    return {
        "phase":"P3.48",
        "authority":"VERIFIABLE_PUBLIC_EXTENSION_MARKETPLACE_WITH_P347_FINAL_INSTALL_AUTHORITY",
        "p347_registry":p347_registry,
    }
