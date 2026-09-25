from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path

import pytest

from p2_document import build_document_map
from p22_formatting import build_formatting_map
from p28_tables import build_table_map
from p321_document_composer import compose_document_plan
from p340_feedback_loop import apply_nested_paragraph_alignment_atomic
from p342_mutation_footprint import (
    apply_document_design_repairs_with_footprint_atomic,
    build_mutation_footprint,
    classify_footprint_grade,
    enforce_preservation_grade,
    normalize_expected_scope,
)


def _write(path: Path, parts: dict[str, bytes], *, year: int = 2026) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in parts.items():
            info = zipfile.ZipInfo(name, (year, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, payload)


def _parts() -> dict[str, bytes]:
    return {
        "mimetype": b"application/hwp+zip",
        "Contents/header.xml": b"<header/>",
        "Contents/section0.xml": b"<section><p>a</p></section>",
        "Contents/content.hpf": b"<package/>",
        "META-INF/manifest.xml": b"<manifest/>",
    }


def test_noop_is_package_identical() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        before = Path(tmp) / "before.hwpx"
        after = Path(tmp) / "after.hwpx"
        _write(before, _parts())
        after.write_bytes(before.read_bytes())
        cert = build_mutation_footprint(before, after, {"changed_parts": []})
        assert cert["preservation"]["actual_grade"] == "PACKAGE_IDENTICAL"
        assert cert["observed"]["changed_parts"] == []
        assert enforce_preservation_grade(cert, "TARGETED_PARTS_ONLY")["passed"]


def test_expected_part_only_is_targeted_grade() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        before = Path(tmp) / "before.hwpx"
        after = Path(tmp) / "after.hwpx"
        parts = _parts()
        _write(before, parts)
        parts2 = dict(parts)
        parts2["Contents/section0.xml"] = b"<section><p>b</p></section>"
        _write(after, parts2)
        cert = build_mutation_footprint(
            before,
            after,
            {
                "changed_parts": ["Contents/section0.xml"],
                "required_changed_parts": ["Contents/section0.xml"],
            },
        )
        assert cert["preservation"]["actual_grade"] == "TARGETED_PARTS_ONLY"
        assert cert["divergence"]["count"] == 0
        assert cert["preservation"]["untouched_part_payloads"]["verified"] == 4


def test_unexpected_part_change_fails_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        before = Path(tmp) / "before.hwpx"
        after = Path(tmp) / "after.hwpx"
        parts = _parts()
        _write(before, parts)
        parts2 = dict(parts)
        parts2["Contents/section0.xml"] = b"<section><p>b</p></section>"
        parts2["Contents/content.hpf"] = b"<package changed='1'/>"
        _write(after, parts2)
        cert = build_mutation_footprint(
            before,
            after,
            {"changed_parts": ["Contents/section0.xml"]},
        )
        assert cert["preservation"]["actual_grade"] == "PACKAGE_VALID_ONLY"
        assert cert["divergence"]["unexpected_changed_parts"] == [
            "Contents/content.hpf"
        ]
        with pytest.raises(ValueError, match="PRESERVATION_GRADE_NOT_MET"):
            enforce_preservation_grade(cert, "TARGETED_PARTS_ONLY")


def test_add_remove_are_separate_divergence_channels() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        before = Path(tmp) / "before.hwpx"
        after = Path(tmp) / "after.hwpx"
        parts = _parts()
        _write(before, parts)
        parts2 = dict(parts)
        parts2.pop("META-INF/manifest.xml")
        parts2["BinData/image1.png"] = b"png"
        _write(after, parts2)
        cert = build_mutation_footprint(before, after, {"changed_parts": []})
        assert cert["divergence"]["unexpected_added_parts"] == ["BinData/image1.png"]
        assert cert["divergence"]["unexpected_removed_parts"] == [
            "META-INF/manifest.xml"
        ]


def test_record_metadata_drift_is_reported_independently() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        before = Path(tmp) / "before.hwpx"
        after = Path(tmp) / "after.hwpx"
        _write(before, _parts(), year=2025)
        _write(after, _parts(), year=2026)
        cert = build_mutation_footprint(before, after, {"changed_parts": []})
        assert cert["preservation"]["actual_grade"] == "TARGETED_PARTS_ONLY"
        assert cert["preservation"]["untouched_record_metadata"]["changed"] == 5
        strict = build_mutation_footprint(
            before,
            after,
            {
                "changed_parts": [],
                "require_untouched_record_metadata": True,
            },
        )
        assert strict["preservation"]["actual_grade"] == "PACKAGE_VALID_ONLY"


def test_expected_scope_is_exact_path_only() -> None:
    with pytest.raises(ValueError):
        normalize_expected_scope({"changed_parts": ["Contents/*.xml"]})
    with pytest.raises(ValueError):
        normalize_expected_scope({"changed_parts": ["../header.xml"]})


def test_real_nested_table_repair_certifies_exact_target_parts() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "real-repair.hwpx"
        compose_document_plan(
            path,
            {
                "preset": "polished-report",
                "blocks": [
                    {"id": "title", "type": "title", "text": "P3.42 footprint integration"},
                    {
                        "id": "table",
                        "type": "table",
                        "rows": 2,
                        "cols": 2,
                        "first_row_header": True,
                        "cells": [
                            ["항목", "설명"],
                            ["A", "장문 표 문단의 정렬을 국소적으로 수정합니다."],
                        ],
                    },
                ],
            },
        )
        doc = build_document_map(path)
        table = build_table_map(path)["tables"][0]
        nested = next(
            item["locator"]
            for item in doc["paragraphs"]
            if "장문 표 문단" in item["text"] and item["body_global_index"] is None
        )
        apply_nested_paragraph_alignment_atomic(path, [nested], alignment="CENTER")
        before_semantic = build_document_map(path)["semantic_sha256"]
        plan = {
            "repair_plan_sha256": "9" * 64,
            "actions": [
                {
                    "action": "LEFT_ALIGN_LONG_TABLE_TEXT",
                    "status": "EXECUTABLE",
                    "reason": "TABLE_LONG_TEXT_CENTERED",
                    "operation": {
                        "op": "align_nested_table_paragraphs",
                        "targets": [nested],
                        "alignment": "LEFT",
                    },
                }
            ],
        }
        receipt = apply_document_design_repairs_with_footprint_atomic(
            path,
            plan,
            expected_revision=1,
            current_revision=1,
        )
        footprint = receipt["mutation_footprint"]
        assert footprint["preservation"]["actual_grade"] == "TARGETED_PARTS_ONLY"
        assert footprint["divergence"]["count"] == 0
        assert footprint["observed"]["changed_parts"] == sorted(
            ["Contents/header.xml", table["section_path"]]
        )
        assert build_document_map(path)["semantic_sha256"] == before_semantic
        after = next(
            item
            for item in build_formatting_map(path)["paragraphs"]
            if item["locator"] == nested
        )
        assert str(
            (after["paragraph_property"]["alignment"] or {}).get("horizontal")
        ).upper() == "LEFT"


@pytest.mark.parametrize(
    ("case", "kwargs", "grade"),
    [
        (
            "identical",
            dict(
                package_identical=True,
                expected_declared=False,
                unexpected_changed=0,
                unexpected_added=0,
                unexpected_removed=0,
                missing_required=0,
            ),
            "PACKAGE_IDENTICAL",
        ),
        (
            "targeted",
            dict(
                package_identical=False,
                expected_declared=True,
                unexpected_changed=0,
                unexpected_added=0,
                unexpected_removed=0,
                missing_required=0,
            ),
            "TARGETED_PARTS_ONLY",
        ),
        (
            "undeclared",
            dict(
                package_identical=False,
                expected_declared=False,
                unexpected_changed=0,
                unexpected_added=0,
                unexpected_removed=0,
                missing_required=0,
            ),
            "PACKAGE_VALID_ONLY",
        ),
        (
            "unexpected",
            dict(
                package_identical=False,
                expected_declared=True,
                unexpected_changed=1,
                unexpected_added=0,
                unexpected_removed=0,
                missing_required=0,
            ),
            "PACKAGE_VALID_ONLY",
        ),
    ],
)
def test_grade_kernel(case: str, kwargs: dict, grade: str) -> None:
    assert classify_footprint_grade(**kwargs) == grade
