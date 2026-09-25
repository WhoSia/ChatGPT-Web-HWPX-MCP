from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from p340r1_capture_pack import read_json, write_json
from p341r1_adjudicate import (
    HUMAN_REVIEW_SCHEMA,
    SCHEMA,
    adjudicate_capture,
    build_human_review_packet,
    write_adjudication,
)


def _write_pack(root: Path, *, complete: bool = True, vary_signature: bool = False) -> Path:
    pack = root / "pack"
    pack.mkdir()

    fixtures = [
        ("A3_RESEARCH", "RESEARCH_BRIEF"),
        ("A3_INSTITUTIONAL", "INSTITUTIONAL_REPORT"),
        ("A3_ACADEMIC", "ACADEMIC_REPORT"),
    ]
    write_json(
        pack / "capture-ready-manifest.json",
        {
            "schema": "authorbench/p341r1-hancom-capture-pack/v1",
            "source": {"runner_commit": "1" * 40},
            "benchmark_authority": {
                "frozen_commit": "2" * 40,
                "workflow_run": 12345,
            },
            "fixtures": [
                {"fixture_id": fixture_id, "archetype": archetype}
                for fixture_id, archetype in fixtures
            ],
        },
    )
    write_json(
        pack / "capture-validation.json",
        {
            "complete": complete,
            "authority": (
                "NATIVE_HANCOM_A3_PAGE_COMPOSITION_COMPLETE"
                if complete
                else "INCOMPLETE_NATIVE_WORLD_CONTACT"
            ),
        },
    )

    for index, (fixture_id, archetype) in enumerate(fixtures):
        capture = pack / "fixtures" / fixture_id / "capture"
        capture.mkdir(parents=True)
        line_counts = [8, 19]
        if vary_signature and index == 2:
            line_counts = [10, 17]
        findings = []
        if index != 1:
            findings.append({"code": "PAGE_BOUNDARY_SINGLE_LINE_BLOCK_RISK"})
        write_json(
            capture / "page-composition-diagnostic.json",
            {
                "authority": "HANCOM_NATIVE_RENDER_EVIDENCE",
                "world_contact_valid": True,
                "page_count": 2,
                "verdict": "PASS_WITH_WARNINGS",
                "findings": findings,
                "page_metrics": [
                    {
                        "page_index": 0,
                        "line_count": line_counts[0],
                        "bottom_margin_ppm": 400_000 + index * 10_000,
                        "vertical_span_ppm": 420_000 - index * 10_000,
                    },
                    {
                        "page_index": 1,
                        "line_count": line_counts[1],
                        "bottom_margin_ppm": 250_000,
                        "vertical_span_ppm": 550_000,
                    },
                ],
            },
        )
    return pack


def test_adjudication_keeps_native_pass_separate_from_human_authority():
    with tempfile.TemporaryDirectory() as tmp:
        pack = _write_pack(Path(tmp))
        result = adjudicate_capture(pack)

        assert result["schema"] == SCHEMA
        assert result["native_world_contact"]["status"] == "PASS"
        assert result["native_world_contact"]["fixture_count"] == 3
        assert result["native_world_contact"]["page_count_total"] == 6
        assert result["human_review"]["status"] == "PENDING_USER_SIGNOFF"
        assert result["human_review"]["authority"] == "NOT_MACHINE_PROMOTABLE"

        codes = {x["code"] for x in result["review_signals"]}
        assert "CROSS_ARCHETYPE_FIRST_PAGE_UNDERFILL_RISK" in codes
        assert "CROSS_ARCHETYPE_COMPOSITION_SIGNATURE_COLLISION" in codes
        assert "PAGE_BOUNDARY_HEURISTIC_REQUIRES_VISUAL_REVIEW" in codes


def test_signature_collision_is_bounded_to_actual_collision():
    with tempfile.TemporaryDirectory() as tmp:
        pack = _write_pack(Path(tmp), vary_signature=True)
        result = adjudicate_capture(pack)
        codes = {x["code"] for x in result["review_signals"]}
        assert "CROSS_ARCHETYPE_FIRST_PAGE_UNDERFILL_RISK" in codes
        assert "CROSS_ARCHETYPE_COMPOSITION_SIGNATURE_COLLISION" not in codes


def test_incomplete_native_capture_fails_closed():
    with tempfile.TemporaryDirectory() as tmp:
        pack = _write_pack(Path(tmp), complete=False)
        with pytest.raises(RuntimeError, match="capture validation is incomplete"):
            adjudicate_capture(pack)


def test_human_review_packet_cannot_silently_promote_machine_review():
    with tempfile.TemporaryDirectory() as tmp:
        pack = _write_pack(Path(tmp))
        adjudication = adjudicate_capture(pack)
        packet = build_human_review_packet(adjudication)

        assert packet["schema"] == HUMAN_REVIEW_SCHEMA
        assert packet["status"] == "PENDING_USER_SIGNOFF"
        assert packet["allowed_statuses"] == ["PASS", "PASS_WITH_RESIDUALS", "HOLD"]
        assert len(packet["questions"]) == 4
        assert packet["native_world_contact"]["status"] == "PASS"


def test_write_adjudication_emits_machine_and_human_receipts():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        pack = _write_pack(root)
        out = root / "adjudication.json"
        human = root / "human-review.json"

        result = write_adjudication(pack, out, human)

        assert read_json(out) == result
        packet = read_json(human)
        assert packet["schema"] == HUMAN_REVIEW_SCHEMA
        assert packet["status"] == "PENDING_USER_SIGNOFF"
