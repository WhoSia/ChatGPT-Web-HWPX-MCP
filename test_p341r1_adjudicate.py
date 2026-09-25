from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from p340r1_capture_pack import read_json, write_json
from p341r1_adjudicate import (
    HUMAN_REVIEW_RECEIPT_SCHEMA,
    HUMAN_REVIEW_SCHEMA,
    REVIEW_CRITERIA,
    SCHEMA,
    adjudicate_capture,
    build_human_review_packet,
    finalize_human_review,
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


def _manual_decisions(packet: dict, status: str = "MANUAL_PASS") -> dict:
    return {
        row["id"]: {
            "status": status,
            "observation": f"Observed {row['id']} in the rendered A3 contact sheet.",
        }
        for row in packet["criteria"]
    }


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
        assert result["human_review"]["required_criteria"] == [
            row["id"] for row in REVIEW_CRITERIA
        ]

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


def test_human_review_packet_requires_criterion_bound_user_observations():
    with tempfile.TemporaryDirectory() as tmp:
        pack = _write_pack(Path(tmp))
        packet = build_human_review_packet(adjudicate_capture(pack))

        assert packet["schema"] == HUMAN_REVIEW_SCHEMA
        assert packet["status"] == "PENDING_USER_SIGNOFF"
        assert packet["allowed_statuses"] == ["PASS", "PASS_WITH_RESIDUALS", "HOLD"]
        assert len(packet["criteria"]) == 4
        assert packet["coverage"] == {
            "required": 4,
            "manual_observed": 0,
            "complete": False,
        }
        assert packet["native_world_contact"]["status"] == "PASS"
        assert all(
            row["required_evidence_class"] == "USER_VISUAL_OBSERVATION"
            for row in packet["criteria"]
        )
        assert packet["evidence_policy"]["machine_pass_is_human_pass"] is False


def test_finalize_human_review_requires_complete_manual_coverage():
    with tempfile.TemporaryDirectory() as tmp:
        packet = build_human_review_packet(adjudicate_capture(_write_pack(Path(tmp))))
        decisions = _manual_decisions(packet)
        decisions.pop("mechanical_styling")
        with pytest.raises(ValueError, match="criterion coverage mismatch"):
            finalize_human_review(
                packet, overall_status="PASS", decisions=decisions
            )


def test_finalize_human_review_rejects_silent_or_inconsistent_pass():
    with tempfile.TemporaryDirectory() as tmp:
        packet = build_human_review_packet(adjudicate_capture(_write_pack(Path(tmp))))
        decisions = _manual_decisions(packet)
        decisions["page_boundary_integrity"]["observation"] = ""
        with pytest.raises(ValueError, match="manual observation required"):
            finalize_human_review(packet, overall_status="PASS", decisions=decisions)

        decisions = _manual_decisions(packet)
        decisions["archetype_differentiation"]["status"] = "MANUAL_PASS_WITH_RESIDUAL"
        with pytest.raises(ValueError, match="overall PASS cannot contain"):
            finalize_human_review(packet, overall_status="PASS", decisions=decisions)


def test_finalize_human_review_emits_explicit_user_authority():
    with tempfile.TemporaryDirectory() as tmp:
        packet = build_human_review_packet(adjudicate_capture(_write_pack(Path(tmp))))
        receipt = finalize_human_review(
            packet,
            overall_status="PASS",
            decisions=_manual_decisions(packet),
        )

        assert receipt["schema"] == HUMAN_REVIEW_RECEIPT_SCHEMA
        assert receipt["status"] == "PASS"
        assert receipt["authority"] == "EXPLICIT_USER_VISUAL_REVIEW"
        assert receipt["coverage"] == {
            "required": 4,
            "manual_observed": 4,
            "complete": True,
        }
        assert all(
            row["evidence_class"] == "USER_VISUAL_OBSERVATION"
            for row in receipt["criteria"]
        )


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
        assert len(packet["criteria"]) == 4
