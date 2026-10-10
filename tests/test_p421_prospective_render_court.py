"""P4.21 negative-control tests: no self-certified native or human PASS."""
from copy import deepcopy

import pytest

from hwpx_mcp.quality.p421_prospective_render_court import (
    adjudicate_shadow_trial, adjudicate_factorial_trial,
    audit_enrollment, registration_contract,
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


def factorial():
    import copy
    src = sample()
    b = copy.deepcopy(src["baseline"])
    c = copy.deepcopy(src["candidate"])
    # Each renderer processes BOTH artifact versions under one environment.
    h_after = copy.deepcopy(b)
    h_after["capture_id"] = "hancom-after"
    h_after["artifact_sha256"] = c["artifact_sha256"]
    r_before = copy.deepcopy(c)
    r_before["capture_id"] = "rival-before"
    r_before["artifact_sha256"] = b["artifact_sha256"]
    return {
        "case_id": src["case_id"],
        "source_sha256": src["source_sha256"],
        "semantic_sha256_before": src["semantic_sha256_before"],
        "semantic_sha256_after": src["semantic_sha256_after"],
        "repairs": src["repairs"],
        "captures": {
            "baseline_hancom": b,
            "candidate_hancom": h_after,
            "baseline_rival": r_before,
            "candidate_rival": c,
        },
        "attested": True,
        "human_review": src["human_review"],
    }


def test_factorial_design_requires_four_cells():
    pair = factorial()
    del pair["captures"]["candidate_rival"]
    result = adjudicate_factorial_trial(pair)
    assert "MISSING_FACTORIAL_CELL" in result["issues"]
    assert result["status"] == "FAIL_PRELIMINARY_COURT"


def test_factorial_clean_synthetic_does_not_certify_native_quality():
    a = adjudicate_factorial_trial(factorial())
    assert a["status"] == "HOLD_UNVERIFIED_NATIVE_CAPTURES_AND_INDEPENDENT_HUMAN_ACCEPTANCE"
    assert set(a["paired_renderer_effects"]) == {"hancom", "rival"}
    assert a["production_release_eligible"] is False
    assert a["blinded_human_acceptance_attested"] is False


@pytest.mark.parametrize("broken,expected", [
    (("candidate_hancom", "renderer_version", "2026"), "HANCOM_VERSION_CONFOUND"),
    (("candidate_rival", "renderer_engine", "unrelated-engine"),
     "RIVAL_VERSION_CONFOUND"),
    (("baseline_rival", "renderer_engine", "pdfium"), "RASTERIZER_NOT_LAYOUT_ENGINE"),
    (("candidate_hancom", "font_inventory_sha256", "1"*64),
     "WITHIN_RENDERER_FONT_DRIFT"),
    (("candidate_rival", "artifact_sha256", "8"*64), "ARTIFACT_RENDERER_CONFOUND"),
])
def test_factorial_confounding_cannot_be_interpreted_as_repair_effect(broken, expected):
    t = factorial()
    key, field, value = broken
    t["captures"][key][field] = value
    result = adjudicate_factorial_trial(t)
    assert expected in result["issues"]
    assert result["production_release_eligible"] is False


def test_factorial_detects_new_hancom_text_loss_and_retains_rival_pair():
    t = factorial()
    t["captures"]["candidate_hancom"]["observation"]["regions"] = [{
        "component_id": "heading", "role": "heading",
        "x": 80, "y": 100, "width": 240, "height": 38,
        "expected_text": "연구", "observed_text": "",
    }]
    result = adjudicate_factorial_trial(t)
    assert "NOVEL_HARD_DEFECT_HANCOM" in result["issues"]
    assert "TEXT_DISAPPEARANCE" in result["paired_renderer_effects"]["hancom"]["candidate_hard_defects"]
    assert result["status"] == "FAIL_PRELIMINARY_COURT"


def test_factorial_reports_reflow_separately_from_semantic_change():
    t = factorial()
    t["captures"]["candidate_hancom"]["page_break_locators"] = ["paragraph-3"]
    result = adjudicate_factorial_trial(t)
    assert result["paired_renderer_effects"]["hancom"]["page_flow_changed"] is True
    assert result["paired_renderer_effects"]["rival"]["page_flow_changed"] is False
    assert result["production_release_eligible"] is False



def test_frozen_calibration_ledger_matches_archive():
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    archived = json.loads((root / "benchmarks/p411_native_calibration.json").read_text(encoding="utf-8"))
    frozen = json.loads((root / "benchmarks/p421_preregistration.json").read_text(encoding="utf-8"))
    source_hashes = {x["source_sha256"].lower() for x in
                     (archived.get("archetypes", []) + archived.get("equations", []))}
    assert set(frozen["known_p411_calibration_source_exclusions"]) == source_hashes
    reg = registration_contract()
    assert [s["case_id"] for s in reg["slots"]] == [
        s["case_id"] for s in frozen["cases"]
    ]
    assert frozen["independent_native_captures_collected"] == 0
    assert frozen["independent_human_reviews_collected"] == 0


def test_enrollment_is_blocked_without_explicit_frozen_exclusions():
    reg = registration_contract()
    entry = dict(reg["slots"][0], source_sha256="a" * 64)
    r = audit_enrollment(reg, [entry])
    assert "EXCLUSION_LEDGER_UNBOUND" in {x["code"] for x in r["issues"]}
    safe = audit_enrollment(reg, [entry], disallowed_source_hashes=["b" * 64])
    assert safe["status"] == "HOLD_UNFILLED_COHORT"
