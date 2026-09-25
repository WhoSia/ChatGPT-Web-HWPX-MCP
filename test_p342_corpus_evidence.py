from __future__ import annotations

import copy
import tempfile
from pathlib import Path

from p335_registry import intake_source, seal_source
from p342_corpus_evidence import (
    build_corpus_coverage_ledger,
    derive_design_generalizations,
    evaluate_source_probes,
)
from test_p335_registry_atlas import fixture, metadata


def test_metadata_only_source_remains_in_denominator() -> None:
    row = intake_source(
        {
            **metadata("meta", "기관M"),
            "access_status": "PUBLICLY_ACCESSIBLE",
            "source_url": "https://example.org/meta",
        }
    )
    verdicts = evaluate_source_probes(row)
    assert verdicts["BYTES_ACQUIRED"]["status"] == "WITHHELD"
    assert verdicts["PACKAGE_VALID"]["status"] == "WITHHELD"
    ledger = build_corpus_coverage_ledger([row])
    assert ledger["denominators"]["registered_sources"] == 1
    assert ledger["denominators"]["metadata_only_sources"] == 1
    summary = {
        item["probe_id"]: item for item in ledger["probe_summary"]
    }
    assert summary["BYTES_ACQUIRED"]["counts"]["WITHHELD"] == 1


def test_public_access_never_promotes_unknown_reuse_rights() -> None:
    row = intake_source(
        {
            **metadata("public", "기관P"),
            "access_status": "PUBLICLY_ACCESSIBLE",
            "source_url": "https://example.org/public",
        }
    )
    assert evaluate_source_probes(row)["REUSE_RIGHTS_EXPLICIT"]["status"] == "WITHHELD"


def test_exact_duplicates_keep_source_denominator_but_one_style_vote() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        a, path, _ = fixture(root, "a", "A", "본문", 10)
        b = intake_source(metadata("b", "B"), path)
        ledger = build_corpus_coverage_ledger([a, b])
        assert ledger["denominators"]["registered_sources"] == 2
        assert ledger["denominators"]["unique_included_byte_documents"] == 1
        assert ledger["denominators"]["exact_duplicate_groups"] == 1


def test_cross_institution_generalization_is_descriptive_only() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        a, _, _ = fixture(root, "a", "A", "가", 12)
        b, _, _ = fixture(root, "b", "B", "나", 12)
        result = derive_design_generalizations(
            [a, b],
            min_documents=2,
            min_institutions=2,
            min_document_share=0.5,
        )
        assert result["status"] == "CANDIDATES"
        assert result["candidates"]
        candidate = result["candidates"][0]
        assert candidate["authority"] == (
            "DESCRIPTIVE_CROSS_INSTITUTION_PATTERN_NOT_NORMATIVE_DEFAULT"
        )
        assert candidate["evidence_class"] == "STRUCTURAL_NATIVE_XML_ONLY"
        assert not candidate["visual_support"]["complete"]


def test_visual_generalization_requires_inspected_control_bytes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        a, _, _ = fixture(root, "a", "A", "가", 12)
        assert evaluate_source_probes(a)["VISUAL_STYLE_GENERALIZATION"]["status"] == "WITHHELD"
        control = {
            "schema": "hwpx-visual-control/v1",
            "source_sha256": a["sha256"],
            "control_sha256": "b" * 64,
            "renderer": "fixture",
            "renderer_version": "1",
            "creation_route": "offline",
            "created_at": "2026-09-26T00:00:00Z",
            "page_sizes_pt": [[595, 842]],
            "page_count": 1,
            "status": "PDF_BYTES_INSPECTED_RENDER_ROUTE_DECLARED",
            "native_semantic_authority": False,
            "authority": "VISUAL_CONTROL_METADATA_ONLY",
        }
        a = seal_source({**a, "controls": [control]})
        assert evaluate_source_probes(a)["VISUAL_STYLE_GENERALIZATION"]["status"] == "PASS"


def test_stale_ledger_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        a, _, _ = fixture(root, "a", "A", "가", 12)
        ledger = build_corpus_coverage_ledger([a])
        tampered = copy.deepcopy(ledger)
        tampered["registry_sha256"] = "0" * 64
        try:
            derive_design_generalizations([a], ledger=tampered)
        except ValueError as exc:
            assert "STALE_CORPUS_COVERAGE_LEDGER" in str(exc)
        else:
            raise AssertionError("stale coverage ledger should fail closed")
