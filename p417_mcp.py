from __future__ import annotations

from p2_document import build_document_map

from mcp.types import ToolAnnotations

from p417_corpus import (
    PRODUCT,
    PHASE,
    attach_render_pair,
    build_dataset,
    corpus_contract,
    infer_archetype,
    mine_style_grammar,
)


def register_p417_tools(core, owned_document=None, refresh_document=None):
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
    write = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)

    @core.mcp.tool(annotations=read)
    def get_p417_document_intelligence_contract() -> dict:
        core._caller_subject()
        return {"ok": True, **corpus_contract()}

    @core.mcp.tool(annotations=read)
    def infer_p417_document_archetype(
        filename: str,
        source_title: str = "",
        text_sample: str = "",
        archetype_hints: list[str] | None = None,
    ) -> dict:
        core._caller_subject()
        return {
            "ok": True,
            **infer_archetype(
                filename=filename,
                source_title=source_title,
                text_sample=text_sample,
                hints=archetype_hints or [],
            ),
        }

    @core.mcp.tool(annotations=read)
    def mine_p417_style_grammar(package_features: dict) -> dict:
        core._caller_subject()
        return {"ok": True, **mine_style_grammar(package_features)}

    @core.mcp.tool(annotations=read)
    def align_p417_render_pair(record: dict, pdf_sha256: str, source: str = "USER_OR_OFFICIAL_PAIR") -> dict:
        core._caller_subject()
        paired = attach_render_pair(record, pdf_sha256=pdf_sha256, source=source)
        return {
            "ok": True,
            "render_pair": paired["render_pair"],
            "record_sha256": paired["record_sha256"],
            "native_visual_authority": False,
        }



    @core.mcp.tool(annotations=read)
    def get_p417_semantic_structure_contract() -> dict:
        core._caller_subject()
        return {"ok": True, **semantic_structure_contract()}

    @core.mcp.tool(annotations=read)
    def get_p417_semantic_document_graph(document_id: str) -> dict:
        if owned_document is None:
            raise RuntimeError("P4.17 semantic graph requires document store binding")
        metadata, path = owned_document(document_id)
        graph = recover_semantic_structure(path)
        return {
            "ok": True,
            "document_id": document_id,
            "revision": int(metadata.get("revision", 1)),
            **graph,
        }

    @core.mcp.tool(annotations=read)
    def classify_p417_native_components(graph: dict) -> dict:
        core._caller_subject()
        return {"ok": True, **classify_native_components(graph)}

    @core.mcp.tool(annotations=read)
    def align_p417_semantic_documents(left_graph: dict, right_graph: dict) -> dict:
        core._caller_subject()
        return {"ok": True, **align_semantic_graphs(left_graph, right_graph)}

    @core.mcp.tool(annotations=read)
    def infer_p417_corpus_document_schema(
        graphs: list[dict],
        support_threshold: float = 0.6,
    ) -> dict:
        core._caller_subject()
        return {
            "ok": True,
            **infer_corpus_schema(graphs, support_threshold=support_threshold),
        }



    @core.mcp.tool(annotations=read)
    def get_p417_transformation_planning_contract() -> dict:
        core._caller_subject()
        return {"ok": True, **transformation_planning_contract()}

    @core.mcp.tool(annotations=read)
    def plan_p417_document_transformation(
        document_id: str,
        intent: dict,
        reference_document_id: str = "",
    ) -> dict:
        if owned_document is None:
            raise RuntimeError("P4.17 transformation planning requires document store binding")
        metadata, path = owned_document(document_id)
        graph = recover_semantic_structure(path)
        document_map = build_document_map(path)
        reference_graph = None
        if str(reference_document_id or "").strip():
            _reference_metadata, reference_path = owned_document(str(reference_document_id).strip())
            reference_graph = recover_semantic_structure(reference_path)
        plan = plan_document_transformation(
            intent=intent,
            semantic_graph=graph,
            document_map=document_map,
            reference_graph=reference_graph,
            archetype=None,
        )
        return {
            "ok": True,
            "document_id": document_id,
            "revision": int(metadata.get("revision", 1)),
            **plan,
        }

    @core.mcp.tool(annotations=read)
    def validate_p417_transformation_plan(plan: dict) -> dict:
        core._caller_subject()
        return {"ok": True, **validate_transformation_plan(plan)}


    @core.mcp.tool(annotations=read)
    def get_p417_transformation_execution_contract() -> dict:
        core._caller_subject()
        return {"ok": True, **transformation_execution_contract()}

    @core.mcp.tool(annotations=write)
    def execute_p417_document_transformation(
        document_id: str,
        expected_revision: int,
        plan: dict,
        reference_transfer: dict | None = None,
        repair_plan: dict | None = None,
        render_evidence: dict | None = None,
        replan_intent: dict | None = None,
        lease_token: str = "",
    ) -> dict:
        if owned_document is None or refresh_document is None:
            raise RuntimeError("P4.17 transformation execution requires document-store bindings")
        metadata, path = owned_document(document_id)
        current_revision = int(metadata.get("revision", 1))
        ingress = metadata.get("source") == "existing-ingress"
        receipt = execute_transformation_atomic(
            path,
            plan,
            expected_revision=int(expected_revision),
            current_revision=current_revision,
            validator=lambda candidate: core.validate_hwpx_package(candidate, ingress=ingress),
            reference_transfer=reference_transfer,
            repair_plan=repair_plan,
            render_evidence=render_evidence,
            replan_intent=replan_intent,
        )
        metadata["revision"] = current_revision + 1
        metadata["last_edit_at"] = core._utc_iso()
        metadata["p417_execution_receipt_sha256"] = receipt["execution_receipt_sha256"]
        if lease_token:
            metadata["_commit_lease_token"] = lease_token
        refreshed = refresh_document(document_id, metadata, path, receipt)
        return {
            "ok": True,
            "document_id": document_id,
            "revision_before": current_revision,
            "revision_after": int(refreshed.get("revision", current_revision + 1)),
            "execution_receipt": receipt,
            **receipt,
        }


    @core.mcp.tool(annotations=write)
    def execute_p417_intent_transformation(
        document_id: str,
        expected_revision: int,
        intent: dict,
        reference_document_id: str = "",
        reference_transfer: dict | None = None,
        repair_plan: dict | None = None,
        render_evidence: dict | None = None,
        replan_intent: dict | None = None,
        lease_token: str = "",
    ) -> dict:
        if owned_document is None or refresh_document is None:
            raise RuntimeError("P4.17 intent execution requires document-store bindings")
        metadata, path = owned_document(document_id)
        current_revision = int(metadata.get("revision", 1))
        graph = recover_semantic_structure(path)
        document_map = build_document_map(path)
        reference_graph = None
        if str(reference_document_id or "").strip():
            _reference_metadata, reference_path = owned_document(str(reference_document_id).strip())
            reference_graph = recover_semantic_structure(reference_path)
        plan = plan_document_transformation(
            intent=intent,
            semantic_graph=graph,
            document_map=document_map,
            reference_graph=reference_graph,
            archetype=None,
        )
        if plan.get("decision") not in {"SAFE_TO_PLAN", "DELEGATE"}:
            return {
                "ok": False,
                "document_id": document_id,
                "revision": current_revision,
                "plan": plan,
                "verdict": str(plan.get("decision") or "ABSTAIN"),
                "transaction": "NOT_EXECUTED",
            }
        ingress = metadata.get("source") == "existing-ingress"
        receipt = execute_transformation_atomic(
            path,
            plan,
            expected_revision=int(expected_revision),
            current_revision=current_revision,
            validator=lambda candidate: core.validate_hwpx_package(candidate, ingress=ingress),
            reference_transfer=reference_transfer,
            repair_plan=repair_plan,
            render_evidence=render_evidence,
            replan_intent=replan_intent,
        )
        metadata["revision"] = current_revision + 1
        metadata["last_edit_at"] = core._utc_iso()
        metadata["p417_execution_receipt_sha256"] = receipt["execution_receipt_sha256"]
        if lease_token:
            metadata["_commit_lease_token"] = lease_token
        refreshed = refresh_document(document_id, metadata, path, receipt)
        return {
            "ok": True,
            "document_id": document_id,
            "revision_before": current_revision,
            "revision_after": int(refreshed.get("revision", current_revision + 1)),
            "plan": plan,
            "execution_receipt": receipt,
            **receipt,
        }

    @core.mcp.tool(annotations=read)
    def verify_p417_post_edit_native_authority(
        document_id: str,
        execution_receipt: dict,
    ) -> dict:
        if owned_document is None:
            raise RuntimeError("P4.17 post-edit native verification requires document-store binding")
        metadata, _path = owned_document(document_id)
        receipt_payload = dict(execution_receipt.get("execution_receipt") or execution_receipt)
        expected_receipt_sha = str(metadata.get("p417_execution_receipt_sha256") or "")
        supplied_receipt_sha = str(receipt_payload.get("execution_receipt_sha256") or "")
        if not expected_receipt_sha or supplied_receipt_sha != expected_receipt_sha:
            raise ValueError("P4.17 execution receipt is not bound to current document metadata")
        current_revision = int(metadata.get("revision") or 1)
        document_sha256 = str(metadata.get("sha256") or "")
        store = getattr(core, "P414_EVIDENCE_STORE", None)
        evidence = None
        if store is not None:
            evidence = store.receipt_for_document(
                document_id=document_id,
                revision=current_revision,
                document_sha256=document_sha256,
            )
        release_head = (
            __import__("os").environ.get("P414_RELEASE_EXACT_HEAD")
            or __import__("os").environ.get("RENDER_GIT_COMMIT")
            or "PENDING_EXACT_HEAD"
        )
        trust = document_native_trust_receipt(
            document_id=document_id,
            revision=current_revision,
            sha256=document_sha256,
            evidence=evidence,
            release_head=release_head,
        )
        return {
            "ok": True,
            **compose_post_edit_native_authority(receipt_payload, trust),
            "native_trust_receipt": trust,
        }

    @core.mcp.tool(annotations=read)
    def summarize_p417_document_intelligence_dataset(records: list[dict]) -> dict:
        core._caller_subject()
        dataset = build_dataset(records)
        return {
            "ok": True,
            "record_count": dataset["record_count"],
            "duplicate_count": dataset["duplicate_count"],
            "institution_count": dataset["institution_count"],
            "archetype_counts": dataset["archetype_counts"],
            "dataset_sha256": dataset["dataset_sha256"],
            "authority": dataset["authority"],
        }

    return {"phase": PHASE, "product": PRODUCT, "authority": "P417_DOCUMENT_INTELLIGENCE_AND_VERIFIED_EXECUTION_SURFACE"}


from p417_semantics import (
    align_semantic_graphs,
    classify_native_components,
    infer_corpus_schema,
    recover_semantic_structure,
    semantic_structure_contract,
)


from p417_planner import (
    plan_document_transformation,
    transformation_planning_contract,
    validate_transformation_plan,
)


from p417_executor import (
    compose_post_edit_native_authority,
    execute_transformation_atomic,
    transformation_execution_contract,
)


from p414_evidence_service import document_native_trust_receipt
