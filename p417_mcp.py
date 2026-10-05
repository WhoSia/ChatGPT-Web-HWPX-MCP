from __future__ import annotations

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


def register_p417_tools(core):
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
