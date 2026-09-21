from __future__ import annotations

from typing import Any


SCHEMA = "chatgpt-web-hwpx-mcp/first-hancom-world-contact/p3.14/v1"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def adjudicate_first_hancom_world_contact(receipt: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(receipt, dict) or receipt.get("schema") != SCHEMA:
        raise ValueError("unsupported P3.14 receipt schema")

    execution = receipt.get("execution") or {}
    integrity = receipt.get("integrity") or {}
    baseline = receipt.get("baseline") or {}
    controls = receipt.get("positive_controls") or {}
    advance = controls.get("advance") or {}
    frame = controls.get("frame") or {}
    cross = receipt.get("cross_version") or {}
    renderer = receipt.get("renderer") or {}

    _require(int(execution.get("expected_fixture_runs", 0)) > 0, "expected fixture count missing")
    _require(
        int(execution.get("succeeded", -1)) == int(execution.get("expected_fixture_runs", 0)),
        "not all fixture runs succeeded",
    )
    _require(int(execution.get("failed", -1)) == 0, "capture failures present")
    _require(execution.get("boundary_ready") is True, "boundary selection is not ready")

    _require(
        int(integrity.get("manifest_document_hashes_checked", 0))
        == int(integrity.get("manifest_document_hashes_matched", -1)),
        "manifest document hash mismatch",
    )
    _require(
        int(integrity.get("render_receipt_document_raster_hash_mismatches", -1)) == 0,
        "render receipt document/raster mismatch",
    )
    _require(
        int(integrity.get("canonical_custody_artifact_hash_mismatches", -1)) == 0,
        "canonical custody artifact mismatch",
    )

    baseline_exact = bool(
        baseline.get("pagination_equal") is True
        and baseline.get("line_break_equal") is True
        and baseline.get("exact_pixel_match") is True
        and float(baseline.get("pixel_diff_ratio", 1.0)) == 0.0
        and float(baseline.get("mae", 1.0)) == 0.0
    )

    advance_sensitive = bool(
        advance.get("predecessor_line_break_equal") is True
        and advance.get("selected_line_break_equal") is False
        and float(advance.get("magnitude_basis_points_over_baseline", 0)) > 0
    )
    frame_sensitive = bool(
        frame.get("predecessor_line_break_equal") is True
        and frame.get("selected_line_break_equal") is False
        and float(frame.get("magnitude_hwpunit", 0)) > 0
    )
    sensitivity_pass = bool(advance_sensitive and frame_sensitive)

    world_contact_pass = bool(
        baseline_exact
        and sensitivity_pass
        and str(renderer.get("name") or "").casefold().startswith("hancom")
        and bool(renderer.get("executable_sha256"))
        and int(renderer.get("dpi", 0)) > 0
    )

    distinct_versions = int(cross.get("distinct_hancom_versions", 0) or 0)
    cross_version_pass = distinct_versions >= 2

    if world_contact_pass and cross_version_pass:
        verdict = "CONDITIONAL_PIXEL_FIDELITY_PROMOTION_CANDIDATE"
    elif world_contact_pass:
        verdict = "FIRST_HANCOM_WORLD_CONTACT_PASS_CROSS_VERSION_HOLD"
    else:
        verdict = "FIRST_HANCOM_WORLD_CONTACT_HOLD"

    return {
        "world_contact_pass": world_contact_pass,
        "baseline_exact_pixel_pass": baseline_exact,
        "positive_sensitivity_pass": sensitivity_pass,
        "advance_boundary_detected": advance_sensitive,
        "frame_boundary_detected": frame_sensitive,
        "cross_version_pass": cross_version_pass,
        "distinct_hancom_versions": distinct_versions,
        "verdict": verdict,
        "authority": (
            "FIRST_TRUSTED_HANCOM_WORLD_CONTACT_AUTHORITY"
            if world_contact_pass
            else "FIRST_HANCOM_WORLD_CONTACT_HOLD"
        ),
        "promotion_ceiling": (
            "CROSS_VERSION_REPLAY_REQUIRED"
            if world_contact_pass and not cross_version_pass
            else "NONE"
            if world_contact_pass and cross_version_pass
            else "WORLD_CONTACT_REPAIR_REQUIRED"
        ),
    }
