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


def register_p417_tools(core, owned_document=None):
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)

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

    return {"phase": PHASE, "product": PRODUCT, "authority": "P417_DOCUMENT_INTELLIGENCE_READ_SURFACE"}


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
