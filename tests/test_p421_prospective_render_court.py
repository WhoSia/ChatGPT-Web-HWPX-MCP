"""P4.21 negative-control tests: no self-certified native or human PASS."""
from copy import deepcopy

import pytest

from hwpx_mcp.quality.p421_prospective_render_court import (
    adjudicate_shadow_trial, audit_enrollment, registration_contract,
)


def sample():
    return {
        "case_id": "p421-pilot-academic_report-01",
        "source_sha256": "a" * 64,
        "semantic_sha256_before": "d" * 64,
        "semantic_sha256_after": "d" * 64,
        "repairs": [{"action": "repair_padding_gap"}],
        "baseline": {
            "artifact_sha256": "b" * 64, "raster_sha256": "e" * 64,
            "font_inventory_sha256": "f" * 64,
            "capture_id": "before", "renderer_engine": "Hancom Hangul",
            "renderer_version": "2024", "host_environment_id": "win-a",
            "page_break_locators": ["p_1"],
            "observation": {"page_width": 1200, "page_height": 1600,
                            "regions": [], "vectors": []},
        },
        "candidate": {
            "artifact_sha256": "c" * 64, "raster_sha256": "1" * 64,
            "font_inventory_sha256": "f" * 64,
            "capture_id": "after", "renderer_engine": "independent-layout-engine",
            "renderer_version": "v1", "host_environment_id": "win-b",
            "page_break_locators": ["p_1"],
            "observation": {"page_width": 1200, "page_height": 1600,
                            "regions": [], "vectors": []},
        },
        "attested": True,
        "human_review": [
            {"reviewer": "alice", "accepted": True},
            {"reviewer": "bob", "accepted": True},
        ],
    }


def test_frozen_cohorts_are_balanced_and_unenrolled():
    reg = registration_contract()
    assert len(reg["slots"]) == 36
    assert sum(x["cohort"] == "pilot" for x in reg["slots"]) == 12
    assert sum(x["cohort"] == "confirmatory" for x in reg["slots"]) == 24
    assert all(x["state"] == "UNENROLLED" for x in reg["slots"])
    assert audit_enrollment(reg, [])["status"] == "HOLD_UNFILLED_COHORT"
    assert len(reg["registration_sha256"]) == 64


def test_source_reuse_between_pilot_and_confirmatory_rejected():
    slots = registration_contract()["slots"]
    result = audit_enrollment(registration_contract(), [
        {"case_id": slots[0]["case_id"], "cohort": "pilot",
         "archetype": "academic_report", "source_sha256": "a" * 64},
        {"case_id": slots[-1]["case_id"], "cohort": "confirmatory",
         "archetype": "image_footnote", "source_sha256": "a" * 64},
    ])
    assert result["status"] == "FAIL_ENROLLMENT"
    assert "SOURCE_REUSE_OR_LEAKAGE" in {x["code"] for x in result["issues"]}


def test_calibration_source_leakage_rejected():
    reg = registration_contract()
    row = {**reg["slots"][0], "source_sha256": "a" * 64}
    result = audit_enrollment(reg, [row],
                              disallowed_source_hashes=["a" * 64])
    assert result["status"] == "FAIL_ENROLLMENT"


def test_fake_attestation_and_fake_human_acceptance_do_not_pass():
    result = adjudicate_shadow_trial(sample())
    assert result["status"] == "HOLD_EXTERNAL_ATTESTATION_AND_HUMAN_REVIEW"
    assert result["renderer_claim_is_unverified"] is True
    assert result["independent_human_review_observed"] is False
    assert result["production_release_eligible"] is False


@pytest.mark.parametrize("change", [
    {"repairs": [{"action": "change_document_meaning"}]},
    {"repairs": [{"action": "repair_padding_gap"}] * 3},
    {"semantic_sha256_after": "8" * 64},
])
def test_semantic_drift_and_unauthorized_repair_fail(change):
    case = sample()
    case.update(change)
    result = adjudicate_shadow_trial(case)
    assert result["status"] == "FAIL_PRELIMINARY_COURT"


def test_same_renderer_with_new_version_is_not_cross_renderer():
    case = sample()
    case["candidate"]["renderer_engine"] = "Hancom Hangul"
    case["candidate"]["renderer_version"] = "2026"
    result = adjudicate_shadow_trial(case)
    assert "CROSS_VERSION_ONLY" in result["issues"]


def test_pdf_rasterizer_does_not_qualify_as_layout_engine():
    case = sample()
    case["candidate"]["renderer_engine"] = "pdfium"
    result = adjudicate_shadow_trial(case)
    assert "RASTERIZER_NOT_LAYOUT_ENGINE" in result["issues"]


def test_invalid_capture_hash_rejected():
    case = sample()
    case["baseline"]["raster_sha256"] = "not-the-real-hash"
    result = adjudicate_shadow_trial(case)
    assert "BASELINE_INVALID_RASTER_SHA256" in result["issues"]


def test_page_flow_change_reported_not_automatically_failed():
    case = sample()
    case["candidate"]["page_break_locators"] = ["p_2", "p_3"]
    result = adjudicate_shadow_trial(case)
    assert result["page_flow_changed"] is True
    assert result["production_release_eligible"] is False


def test_invented_extra_observation_does_not_change_source():
    case = sample()
    original = deepcopy(case)
    a = adjudicate_shadow_trial(case)
    b = adjudicate_shadow_trial(case)
    assert a == b
    assert case == original
    assert len(a["receipt_sha256"]) == 64


def test_candidate_new_missing_text_is_blocking():
    case = sample()
    case["candidate"]["observation"]["regions"] = [{
        "component_id": "title", "role": "heading",
        "x": 100, "y": 200, "width": 250, "height": 40,
        "expected_text": "실험", "observed_text": "",
    }]
    result = adjudicate_shadow_trial(case)
    assert result["status"] == "FAIL_PRELIMINARY_COURT"
    assert "TEXT_DISAPPEARANCE" in result["candidate_defects"]
    assert "NOVEL_HARD_DEFECT" in result["issues"]
