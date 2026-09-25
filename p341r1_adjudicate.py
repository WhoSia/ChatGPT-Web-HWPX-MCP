from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from p340r1_capture_pack import read_json, sha256_file, write_json

SCHEMA = "chatgpt-web-hwpx-mcp/p3.41-r1-adjudication/v1"
HUMAN_REVIEW_SCHEMA = "chatgpt-web-hwpx-mcp/p3.41-r1-human-review/v1"

FIRST_PAGE_BOTTOM_MARGIN_RISK_PPM = 350_000
FIRST_PAGE_VERTICAL_SPAN_RISK_PPM = 450_000


def _load_diagnostics(pack: Path) -> list[dict[str, Any]]:
    manifest = read_json(pack / "capture-ready-manifest.json")
    rows: list[dict[str, Any]] = []
    for fixture in manifest.get("fixtures", []):
        fixture_id = str(fixture["fixture_id"])
        diagnostic_path = (
            pack
            / "fixtures"
            / fixture_id
            / "capture"
            / "page-composition-diagnostic.json"
        )
        diagnostic = read_json(diagnostic_path)
        if diagnostic.get("authority") != "HANCOM_NATIVE_RENDER_EVIDENCE":
            raise RuntimeError(
                f"{fixture_id} lacks HANCOM_NATIVE_RENDER_EVIDENCE authority"
            )
        if not diagnostic.get("world_contact_valid"):
            raise RuntimeError(f"{fixture_id} native world contact is invalid")
        rows.append(
            {
                "fixture_id": fixture_id,
                "archetype": str(fixture["archetype"]),
                "diagnostic_path": diagnostic_path,
                "diagnostic": diagnostic,
            }
        )
    if not rows:
        raise RuntimeError("capture pack contains no fixtures")
    return rows


def _composition_signature(diagnostic: dict[str, Any]) -> dict[str, Any]:
    metrics = diagnostic.get("page_metrics") or []
    return {
        "page_count": int(diagnostic.get("page_count") or len(metrics)),
        "line_counts": [int(x.get("line_count", 0)) for x in metrics],
    }


def _first_page_underfill(row: dict[str, Any]) -> bool:
    metrics = row["diagnostic"].get("page_metrics") or []
    if not metrics:
        return False
    first = metrics[0]
    return (
        int(first.get("bottom_margin_ppm", 0)) >= FIRST_PAGE_BOTTOM_MARGIN_RISK_PPM
        and int(first.get("vertical_span_ppm", 1_000_000))
        <= FIRST_PAGE_VERTICAL_SPAN_RISK_PPM
    )


def adjudicate_capture(pack: Path) -> dict[str, Any]:
    pack = pack.resolve()
    validation = read_json(pack / "capture-validation.json")
    if not validation.get("complete"):
        raise RuntimeError("P3.41-R1 capture validation is incomplete")
    if validation.get("authority") != "NATIVE_HANCOM_A3_PAGE_COMPOSITION_COMPLETE":
        raise RuntimeError(
            "capture validation lacks NATIVE_HANCOM_A3_PAGE_COMPOSITION_COMPLETE"
        )

    manifest = read_json(pack / "capture-ready-manifest.json")
    rows = _load_diagnostics(pack)

    fixtures: list[dict[str, Any]] = []
    for row in rows:
        diagnostic = row["diagnostic"]
        fixtures.append(
            {
                "fixture_id": row["fixture_id"],
                "archetype": row["archetype"],
                "diagnostic_sha256": sha256_file(row["diagnostic_path"]),
                "page_count": int(diagnostic["page_count"]),
                "verdict": diagnostic["verdict"],
                "finding_codes": [
                    str(x.get("code")) for x in diagnostic.get("findings", [])
                ],
                "composition_signature": _composition_signature(diagnostic),
                "first_page_underfill_risk": _first_page_underfill(row),
            }
        )

    review_signals: list[dict[str, Any]] = []

    underfilled = [x for x in fixtures if x["first_page_underfill_risk"]]
    if len(underfilled) >= 2:
        review_signals.append(
            {
                "code": "CROSS_ARCHETYPE_FIRST_PAGE_UNDERFILL_RISK",
                "severity": "MEDIUM",
                "authority": "NATIVE_GEOMETRY_REVIEW_SIGNAL",
                "archetypes": [x["archetype"] for x in underfilled],
                "thresholds": {
                    "bottom_margin_ppm_gte": FIRST_PAGE_BOTTOM_MARGIN_RISK_PPM,
                    "vertical_span_ppm_lte": FIRST_PAGE_VERTICAL_SPAN_RISK_PPM,
                },
                "interpretation": (
                    "Multiple archetypes leave a large first-page lower whitespace field. "
                    "This is a review signal, not automatic mutation authority."
                ),
            }
        )

    signatures = {
        (
            x["composition_signature"]["page_count"],
            tuple(x["composition_signature"]["line_counts"]),
        )
        for x in fixtures
    }
    if len(fixtures) >= 2 and len(signatures) == 1:
        review_signals.append(
            {
                "code": "CROSS_ARCHETYPE_COMPOSITION_SIGNATURE_COLLISION",
                "severity": "MEDIUM",
                "authority": "CROSS_FIXTURE_REVIEW_SIGNAL",
                "signature": fixtures[0]["composition_signature"],
                "archetypes": [x["archetype"] for x in fixtures],
                "interpretation": (
                    "All archetypes share the same coarse page-count/line-count signature. "
                    "Review whether archetype differentiation is sufficiently compositional "
                    "rather than mostly typographic/content-level."
                ),
            }
        )

    boundary_heuristics = [
        x
        for x in fixtures
        if "PAGE_BOUNDARY_SINGLE_LINE_BLOCK_RISK" in x["finding_codes"]
    ]
    if boundary_heuristics:
        review_signals.append(
            {
                "code": "PAGE_BOUNDARY_HEURISTIC_REQUIRES_VISUAL_REVIEW",
                "severity": "LOW",
                "authority": "PAGE_LOCAL_PDF_BLOCK_HEURISTIC",
                "archetypes": [x["archetype"] for x in boundary_heuristics],
                "interpretation": (
                    "Page-local PDF blocks cannot prove cross-page paragraph identity. "
                    "Keep the warning observational until a human or durable document locator resolves it."
                ),
            }
        )

    return {
        "schema": SCHEMA,
        "phase": "P3.41-R1",
        "source": {
            "runner_commit": manifest["source"]["runner_commit"],
            "frozen_benchmark_commit": manifest["benchmark_authority"]["frozen_commit"],
            "frozen_workflow_run": manifest["benchmark_authority"]["workflow_run"],
            "capture_validation_sha256": sha256_file(pack / "capture-validation.json"),
        },
        "native_world_contact": {
            "status": "PASS",
            "authority": validation["authority"],
            "fixture_count": len(fixtures),
            "page_count_total": sum(x["page_count"] for x in fixtures),
        },
        "fixtures": fixtures,
        "review_signals": review_signals,
        "review_signal_count": len(review_signals),
        "human_review": {
            "status": "PENDING_USER_SIGNOFF",
            "authority": "NOT_MACHINE_PROMOTABLE",
        },
        "recommended_authority": (
            "NATIVE_WORLD_CONTACT_PASS / CROSS_ARCHETYPE_VISUAL_GENERALIZATION_REVIEW_REQUIRED "
            "/ HUMAN_REVIEW_PENDING"
        ),
    }


def build_human_review_packet(adjudication: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": HUMAN_REVIEW_SCHEMA,
        "phase": "P3.41-R1",
        "source": adjudication["source"],
        "native_world_contact": adjudication["native_world_contact"],
        "review_signals": adjudication["review_signals"],
        "questions": [
            {
                "id": "first_page_whitespace",
                "question": (
                    "Are the large first-page whitespace fields appropriate for these short "
                    "two-page archetypes, or do they feel prematurely page-broken?"
                ),
            },
            {
                "id": "archetype_differentiation",
                "question": (
                    "Do RESEARCH_BRIEF, INSTITUTIONAL_REPORT, and ACADEMIC_REPORT feel "
                    "sufficiently different in page-level composition, not only typography?"
                ),
            },
            {
                "id": "page_boundary",
                "question": (
                    "Does any page boundary visibly split a sentence, table, heading, or "
                    "semantic unit awkwardly?"
                ),
            },
            {
                "id": "mechanical_styling",
                "question": (
                    "Is there any distracting mechanical repetition, imbalance, or density "
                    "problem that should block P3.41 closure?"
                ),
            },
        ],
        "allowed_statuses": ["PASS", "PASS_WITH_RESIDUALS", "HOLD"],
        "status": "PENDING_USER_SIGNOFF",
    }


def write_adjudication(pack: Path, output: Path, human_output: Path | None = None) -> dict[str, Any]:
    adjudication = adjudicate_capture(pack)
    write_json(output, adjudication)
    if human_output is not None:
        write_json(human_output, build_human_review_packet(adjudication))
    return adjudication


__all__ = [
    "FIRST_PAGE_BOTTOM_MARGIN_RISK_PPM",
    "FIRST_PAGE_VERTICAL_SPAN_RISK_PPM",
    "adjudicate_capture",
    "build_human_review_packet",
    "write_adjudication",
]
