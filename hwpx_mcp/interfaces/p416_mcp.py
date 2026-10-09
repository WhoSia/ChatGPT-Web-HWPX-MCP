from __future__ import annotations

from mcp.types import ToolAnnotations

from hwpx_mcp.evidence.p416_generation_manifest import (
    PHASE,
    PRODUCT,
    classify_reproduction,
    minimal_sufficient_generation_witness,
    verify_generation_manifest,
    witness_ablation,
)


def register_p416_tools(core, owned_document):
    read = ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        openWorldHint=False,
    )

    @core.mcp.tool(annotations=read)
    def get_p416_generation_manifest_contract() -> dict:
        core._caller_subject()
        return {
            "ok": True,
            "phase": PHASE,
            "product": PRODUCT,
            "authority": "P416_REPRODUCIBLE_GENERATION_MANIFEST_CONTRACT",
            "native_rule": (
                "ARTIFACT_OR_REPRODUCTION_SUCCESS_NEVER_IMPLIES_NATIVE_HANCOM_PASS"
            ),
            "offline_verification": True,
            "raw_private_inputs_stored_by_default": False,
        }

    @core.mcp.tool(annotations=read)
    def verify_p416_generation_manifest(
        manifest: dict,
        artifact_sha256: str = "",
    ) -> dict:
        core._caller_subject()
        return {
            "ok": True,
            **verify_generation_manifest(
                manifest,
                artifact_sha256=artifact_sha256 or None,
            ),
        }

    @core.mcp.tool(annotations=read)
    def get_p416_document_generation_manifest(document_id: str) -> dict:
        metadata, _path = owned_document(document_id)
        manifest = metadata.get("p416_generation_manifest")
        if not isinstance(manifest, dict):
            raise FileNotFoundError(
                "P4.16 generation manifest not recorded for this document"
            )
        return {
            "ok": True,
            "document_id": document_id,
            "revision": int(metadata.get("revision", 1)),
            "manifest": manifest,
            "manifest_sha256": manifest.get("manifest_sha256"),
        }

    @core.mcp.tool(annotations=read)
    def get_p416_minimal_generation_witness(manifest: dict) -> dict:
        core._caller_subject()
        return {
            "ok": True,
            "witness": minimal_sufficient_generation_witness(manifest),
            "ablation": witness_ablation(manifest),
        }

    @core.mcp.tool(annotations=read)
    def compare_p416_generation_reproduction(
        reference_manifest: dict,
        candidate_manifest: dict,
        reference_structure_sha256: str = "",
        candidate_structure_sha256: str = "",
        reference_semantic_sha256: str = "",
        candidate_semantic_sha256: str = "",
    ) -> dict:
        core._caller_subject()
        return {
            "ok": True,
            **classify_reproduction(
                reference_manifest,
                candidate_manifest,
                reference_structure_sha256=(
                    reference_structure_sha256 or None
                ),
                candidate_structure_sha256=(
                    candidate_structure_sha256 or None
                ),
                reference_semantic_sha256=(
                    reference_semantic_sha256 or None
                ),
                candidate_semantic_sha256=(
                    candidate_semantic_sha256 or None
                ),
            ),
        }

    return {
        "phase": PHASE,
        "product": PRODUCT,
        "authority": "P416_GENERATION_PROVENANCE_READ_SURFACE",
    }
