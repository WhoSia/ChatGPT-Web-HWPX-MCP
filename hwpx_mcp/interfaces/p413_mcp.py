from __future__ import annotations

from mcp.types import ToolAnnotations

from hwpx_mcp.evidence.p413_evidence_service import (
    compare_evidence_drift,
    document_visual_authority_receipt,
    evidence_health_summary,
    evaluate_native_evidence_receipt,
    load_promoted_baseline,
    public_authoring_trust_status,
    release_manifest,
)

def register_p413_tools(core):
    read=ToolAnnotations(readOnlyHint=True,destructiveHint=False,openWorldHint=False)

    @core.mcp.tool(annotations=read)
    def get_p413_release_manifest() -> dict:
        core._caller_subject()
        return {"ok":True,**release_manifest()}

    @core.mcp.tool(annotations=read)
    def get_p413_native_evidence_baseline() -> dict:
        core._caller_subject()
        return {"ok":True,**load_promoted_baseline()}

    @core.mcp.tool(annotations=read)
    def get_p413_evidence_health() -> dict:
        core._caller_subject()
        return {"ok":True,**evidence_health_summary()}

    @core.mcp.tool(annotations=read)
    def validate_p413_native_evidence_receipt(receipt: dict) -> dict:
        core._caller_subject()
        return {"ok":True,**evaluate_native_evidence_receipt(receipt)}

    @core.mcp.tool(annotations=read)
    def compare_p413_native_evidence_drift(candidate: dict) -> dict:
        core._caller_subject()
        return {"ok":True,**compare_evidence_drift(candidate)}

    @core.mcp.tool(annotations=read)
    def get_p413_public_authoring_trust_status() -> dict:
        core._caller_subject()
        return {"ok":True,**public_authoring_trust_status()}

    @core.mcp.tool(annotations=read)
    def get_p413_document_visual_authority_receipt(document_id: str) -> dict:
        metadata=core._load_metadata(document_id)
        core._require_owner(metadata)
        return {
            "ok":True,
            **document_visual_authority_receipt(
                document_id=document_id,
                revision=int(metadata.get("revision") or 1),
                sha256=str(metadata.get("sha256") or ""),
            ),
        }

    return {
        "phase":"P4.13",
        "product":"0.38.0-p4.13",
        "authority":"CONTINUOUS_HANCOM_EVIDENCE_AND_PUBLIC_AUTHORING_TRUST_SERVICE",
    }
