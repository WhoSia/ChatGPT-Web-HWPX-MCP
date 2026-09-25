from __future__ import annotations

import csv
import tempfile
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from p321_document_composer import compose_document_plan

from p341_page_composition import (
    analyze_page_primitive,
    compare_page_composition_diagnostics,
    diagnose_page_composition,
    page_composition_contract,
    plan_render_guided_layout_policy,
)

ROOT = Path(__file__).resolve().parent


def _line(y: int, *, locator: str, x: int = 100, width: int = 400, height: int = 20) -> dict:
    return {
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "baseline": y + height,
        "paragraph_locator": locator,
        "text_sha256": "a" * 64,
    }


def _renderer() -> dict:
    return {
        "hancom_native": True,
        "executable_sha256": "b" * 64,
        "dpi": 144,
    }


def test_contract_is_polyglot_and_non_scalar():
    contract = page_composition_contract()
    assert contract["phase"] == "P3.41"
    assert contract["polyglot"]["rust"].startswith("deterministic")
    assert "No scalar beauty score." in contract["non_claims"]


def test_balanced_page_can_pass():
    lines = [_line(120 + i * 30, locator=f"p{i // 3}") for i in range(28)]
    capture = {"pages": [{"page_index": 0, "width_px": 1000, "height_px": 1400, "raster_sha256": "c" * 64, "line_boxes": lines}]}
    result = diagnose_page_composition(capture, renderer=_renderer(), archetype="POLISHED_REPORT")
    assert result["authority"] == "HANCOM_NATIVE_RENDER_EVIDENCE"
    assert result["verdict"] in {"PASS", "PASS_WITH_WARNINGS"}
    assert "PAGE_COMPOSITION_OVERFULL" not in [x["code"] for x in result["findings"]]


def test_overfull_page_is_named_finding_not_beauty_score():
    lines = [_line(35 + i * 21, locator=f"p{i // 4}", width=820, height=19) for i in range(61)]
    capture = {"pages": [{"page_index": 0, "width_px": 1000, "height_px": 1400, "raster_sha256": "d" * 64, "line_boxes": lines}]}
    result = diagnose_page_composition(capture, archetype="POLISHED_REPORT")
    codes = [x["code"] for x in result["findings"]]
    assert "PAGE_COMPOSITION_OVERFULL" in codes
    assert "beauty_score" not in result


def test_single_line_cross_page_paragraph_is_transition_risk():
    p0 = [_line(150 + i * 35, locator=f"a{i}") for i in range(8)] + [_line(1000, locator="carry")]
    p1 = [_line(120, locator="carry")] + [_line(180 + i * 35, locator=f"b{i}") for i in range(8)]
    capture = {"pages": [
        {"page_index": 0, "width_px": 1000, "height_px": 1400, "raster_sha256": "e" * 64, "line_boxes": p0},
        {"page_index": 1, "width_px": 1000, "height_px": 1400, "raster_sha256": "f" * 64, "line_boxes": p1},
    ]}
    result = diagnose_page_composition(capture, archetype="RESEARCH_BRIEF")
    assert "PAGE_BOUNDARY_SINGLE_LINE_PARAGRAPH" in [x["code"] for x in result["findings"]]
    policy = plan_render_guided_layout_policy(result)
    assert policy["executable_count"] == 0
    assert any(x["action"] == "REVIEW_KEEP_TOGETHER_OR_REPAGINATION" for x in policy["actions"])


def test_page_local_pdf_blocks_do_not_claim_cross_page_paragraph_identity():
    p0 = [_line(160 + i * 35, locator=f"page:0/block:{i}") for i in range(7)] + [_line(1050, locator="page:0/block:99")]
    p1 = [_line(120, locator="page:1/block:0")] + [_line(190 + i * 35, locator=f"page:1/block:{i+1}") for i in range(7)]
    capture = {"pages": [
        {"page_index": 0, "width_px": 1000, "height_px": 1400, "raster_sha256": "8" * 64, "line_boxes": p0},
        {"page_index": 1, "width_px": 1000, "height_px": 1400, "raster_sha256": "9" * 64, "line_boxes": p1},
    ]}
    result = diagnose_page_composition(capture, archetype="RESEARCH_BRIEF")
    codes = [x["code"] for x in result["findings"]]
    assert "PAGE_BOUNDARY_SINGLE_LINE_PARAGRAPH" not in codes
    assert "PAGE_BOUNDARY_SINGLE_LINE_BLOCK_RISK" in codes
    finding = next(x for x in result["findings"] if x["code"] == "PAGE_BOUNDARY_SINGLE_LINE_BLOCK_RISK")
    assert finding["evidence"]["identity_authority"] == "PAGE_LOCAL_PDF_BLOCK_HEURISTIC"


def test_native_comparison_preserves_authority_boundary():
    base = {
        "authority": "HANCOM_NATIVE_RENDER_EVIDENCE",
        "capture_sha256": "1" * 64,
        "findings": [{"code": "PAGE_COMPOSITION_OVERFULL", "scope": "PAGE_1"}],
    }
    after = {
        "authority": "HANCOM_NATIVE_RENDER_EVIDENCE",
        "capture_sha256": "2" * 64,
        "findings": [],
    }
    result = compare_page_composition_diagnostics(base, after)
    assert result["native_before_after_available"] is True
    assert result["resolved"] == [{"code": "PAGE_COMPOSITION_OVERFULL", "scope": "PAGE_1"}]


def test_composer_non_heading_carriers_do_not_inherit_outline_semantics():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "semantic-isolation.hwpx"
        compose_document_plan(out, {
            "preset": "academic-report",
            "blocks": [
                {"id": "h1", "type": "heading", "level": 1, "text": "분석 설계"},
                {"id": "body", "type": "paragraph", "text": "본문은 개요 메타데이터를 상속하지 않는다."},
                {"id": "table", "type": "table", "rows": 1, "cols": 1, "cells": [["callout"]]},
            ],
        })
        with zipfile.ZipFile(out) as archive:
            header = etree.fromstring(archive.read("Contents/header.xml"))
            section = etree.fromstring(archive.read("Contents/section0.xml"))
        para_props = {
            e.get("id"): e
            for e in header.iter()
            if etree.QName(e).localname == "paraPr"
        }
        paragraphs = [e for e in section.iter() if etree.QName(e).localname == "p"]
        body = next(
            p for p in paragraphs
            if "".join((e.text or "") for e in p.iter() if etree.QName(e).localname == "t").strip()
            == "본문은 개요 메타데이터를 상속하지 않는다."
        )
        table_anchor = next(
            p for p in paragraphs
            if any(etree.QName(e).localname == "tbl" for e in p.iter())
        )
        for paragraph in (body, table_anchor):
            prop = para_props[paragraph.get("paraPrIDRef")]
            heading = next(e for e in prop.iter() if etree.QName(e).localname == "heading")
            assert heading.get("type") == "NONE"


def test_golden_page_kernel_fixture_matches_python_reference():
    fixture = ROOT / "benchmarks" / "p341_page_geometry_golden.tsv"
    with fixture.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert rows
    for row in rows:
        primitive = {
            "width_px": int(row["width"]),
            "height_px": int(row["height"]),
            "line_count": int(row["line_count"]),
            "left_px": int(row["left"]),
            "right_px": int(row["right"]),
            "top_px": int(row["top"]),
            "bottom_px": int(row["bottom"]),
            "line_area_px2": int(row["line_area"]),
            "largest_internal_gap_px": int(row["largest_gap"]),
            "top_area_px2": int(row["top_area"]),
            "bottom_area_px2": int(row["bottom_area"]),
        }
        actual = analyze_page_primitive(primitive, row["archetype"])["finding_codes"]
        expected = [x for x in row["expected_codes"].split(",") if x]
        assert actual == expected, row["case"]
