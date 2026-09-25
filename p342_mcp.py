from __future__ import annotations

import tempfile
from pathlib import Path

from p342_corpus_evidence import (
    build_corpus_coverage_ledger,
    corpus_evidence_contract,
    derive_design_generalizations,
)
from p342_mutation_footprint import (
    build_mutation_footprint,
    enforce_preservation_grade,
    mutation_footprint_contract,
)


def register_p342_tools(core, owned_document, corpus_registry):
    def owner() -> str:
        return core._caller_subject()

    def page(rows: list[dict], offset: int, limit: int) -> dict:
        if offset < 0 or not 1 <= limit <= 20:
            raise ValueError("INVALID_PAGE_BOUNDS")
        return {
            "total": len(rows),
            "items": rows[offset : offset + limit],
            "next_offset": offset + limit if offset + limit < len(rows) else None,
        }

    @core.mcp.tool()
    def get_mutation_footprint_contract() -> dict:
        """Return P3.42 exact-part mutation certification and preservation-grade semantics."""
        owner()
        return {"ok": True, **mutation_footprint_contract()}

    @core.mcp.tool()
    def certify_document_revision_mutation_footprint(
        document_id: str,
        before_revision: int,
        after_revision: int,
        expected_scope: dict,
        required_grade: str = "TARGETED_PARTS_ONLY",
    ) -> dict:
        """Measure package-part divergence between two owned durable revisions and enforce one grade."""
        subject = owner()
        metadata, _ = owned_document(document_id)
        current = int(metadata["revision"])
        before_revision_i = int(before_revision)
        after_revision_i = int(after_revision)
        if (
            before_revision_i < 1
            or after_revision_i < 1
            or before_revision_i > current
            or after_revision_i > current
        ):
            raise ValueError("REVISION_OUTSIDE_DURABLE_HISTORY")
        before = core.DOCUMENT_STORE.load_revision(document_id, before_revision_i)
        after = core.DOCUMENT_STORE.load_revision(document_id, after_revision_i)
        if before is None or after is None:
            raise FileNotFoundError("DURABLE_REVISION_BYTES_NOT_AVAILABLE")
        if before["owner_subject"] != subject or after["owner_subject"] != subject:
            raise PermissionError("DURABLE_REVISION_OWNER_MISMATCH")

        with tempfile.TemporaryDirectory(prefix="p342-footprint-") as tmp:
            root = Path(tmp)
            before_path = root / "before.hwpx"
            after_path = root / "after.hwpx"
            before_path.write_bytes(before["bytes"])
            after_path.write_bytes(after["bytes"])
            certificate = build_mutation_footprint(
                before_path,
                after_path,
                expected_scope=expected_scope,
            )
        enforcement = enforce_preservation_grade(certificate, required_grade)
        return {
            "ok": True,
            "document_id": document_id,
            "before_revision": before_revision_i,
            "after_revision": after_revision_i,
            "current_revision": current,
            "certificate": certificate,
            "enforcement": enforcement,
            "authority": "DURABLE_REVISION_BYTES_MEASURED_NOT_ASSERTED",
        }

    @core.mcp.tool()
    def get_corpus_evidence_contract() -> dict:
        """Return P3.42 probe→verdict→coverage-ledger semantics and denominator policy."""
        owner()
        return {"ok": True, **corpus_evidence_contract()}

    @core.mcp.tool()
    def query_corpus_coverage_ledger(
        probe_ids: list[str] | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> dict:
        """Build an owner-scoped coverage ledger without dropping withheld/not-applicable sources."""
        records = corpus_registry.records(owner())
        ledger = build_corpus_coverage_ledger(
            records,
            probe_ids=probe_ids or None,
        )
        rows = list(ledger["source_verdicts"])
        return {
            "ok": True,
            **{k: v for k, v in ledger.items() if k != "source_verdicts"},
            **page(rows, int(offset), int(limit)),
        }

    @core.mcp.tool()
    def query_evidence_grounded_design_generalizations(
        min_documents: int = 2,
        min_institutions: int = 2,
        min_document_share: float = 0.2,
        offset: int = 0,
        limit: int = 20,
    ) -> dict:
        """Return descriptive cross-institution style candidates; never choose a normative winner."""
        records = corpus_registry.records(owner())
        ledger = build_corpus_coverage_ledger(records)
        result = derive_design_generalizations(
            records,
            ledger=ledger,
            min_documents=int(min_documents),
            min_institutions=int(min_institutions),
            min_document_share=float(min_document_share),
        )
        rows = list(result["candidates"])
        return {
            "ok": True,
            **{k: v for k, v in result.items() if k != "candidates"},
            **page(rows, int(offset), int(limit)),
        }

    return {
        "phase": "P3.42",
        "mutation_contract": mutation_footprint_contract(),
        "corpus_contract": corpus_evidence_contract(),
    }
