from __future__ import annotations

from mcp.types import ToolAnnotations

from p415_authority import (
    PRODUCT,
    authority_contract,
    evaluate_admission,
    evaluate_rollback,
    reconcile_native_hosted,
    verify_continuous_production_attestation,
    verify_graph,
)


def register_p415_tools(core):
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)

    @core.mcp.tool(annotations=read)
    def get_p415_release_authority_contract() -> dict:
        core._caller_subject()
        return {"ok": True, **authority_contract()}

    @core.mcp.tool(annotations=read)
    def verify_p415_release_evidence_graph(graph: dict) -> dict:
        core._caller_subject()
        return {"ok": True, **verify_graph(graph)}

    @core.mcp.tool(annotations=read)
    def evaluate_p415_release_admission(graph: dict, claim_native_fidelity: bool = False) -> dict:
        core._caller_subject()
        return {"ok": True, **evaluate_admission(graph, claim_native_fidelity=claim_native_fidelity)}

    @core.mcp.tool(annotations=read)
    def reconcile_p415_native_hosted_conformance(hosted: dict, native: dict | None = None) -> dict:
        core._caller_subject()
        return {"ok": True, **reconcile_native_hosted(hosted=hosted, native=native)}

    @core.mcp.tool(annotations=read)
    def verify_p415_continuous_production_attestation(
        expected_head: str,
        observed_head: str,
        observed_product: str,
        boundary_pass: bool,
        expected_product: str = PRODUCT,
    ) -> dict:
        core._caller_subject()
        return {"ok": True, **verify_continuous_production_attestation(
            expected_head=expected_head,
            expected_product=expected_product,
            observed_head=observed_head,
            observed_product=observed_product,
            boundary_pass=boundary_pass,
        )}

    @core.mcp.tool(annotations=read)
    def evaluate_p415_rollback_authority(
        current_head: str,
        target_release: dict,
        ancestry_proven: bool,
        artifact_sha256_observed: str,
    ) -> dict:
        core._caller_subject()
        return {"ok": True, **evaluate_rollback(
            current_head=current_head,
            target_release=target_release,
            ancestry_proven=ancestry_proven,
            artifact_sha256_observed=artifact_sha256_observed,
        )}

    return {"phase": "P4.15", "product": PRODUCT, "authority": "P415_READ_ONLY_AUTHORITY_SURFACE"}
