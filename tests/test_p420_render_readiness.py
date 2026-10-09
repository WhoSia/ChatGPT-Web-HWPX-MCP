"""P4.20 evidence boundaries: passing ZIP does not mean native visual PASS."""
from hwpx_mcp.quality.p420_render_readiness import assess_render_readiness


def _capture():
    return {
        "source_sha256": "a" * 64,
        "renderer": "Hancom Hangul",
        "renderer_version": "test-fixture-only",
        "pages": [{
            "page_index": 0,
            "width_px": 1000,
            "height_px": 1400,
            "raster_sha256": "b" * 64,
            "line_boxes": [],
        }],
    }


def test_static_pass_stays_on_native_hold():
    r = assess_render_readiness(artifact_sha256="a" * 64, structural_valid=True)
    assert r["status"] == "HOLD_NATIVE_CAPTURE"
    assert r["release_eligible"] is False


def test_mismatched_native_source_is_rejected():
    r = assess_render_readiness(
        artifact_sha256="c" * 64, structural_valid=True,
        capture=_capture(), observation={"page_count": 1},
    )
    assert r["status"] == "FAIL_SOURCE_BINDING"


def test_clean_unattested_capture_cannot_claim_production_pass():
    r = assess_render_readiness(
        artifact_sha256="a" * 64, structural_valid=True,
        capture=_capture(), observation={
            "page_count": 1, "page_width": 1000, "page_height": 1400,
            "regions": [], "vectors": [],
        },
    )
    assert r["status"] == "HOLD_INDEPENDENT_NATIVE_ATTESTATION"
    assert r["release_eligible"] is False


def test_missing_observed_text_is_typed_visual_failure():
    r = assess_render_readiness(
        artifact_sha256="a" * 64, structural_valid=True,
        capture=_capture(), observation={
            "page_count": 1, "page_width": 1000, "page_height": 1400,
            "regions": [{
                "component_id": "headline", "role": "title",
                "x": 100, "y": 100, "width": 200, "height": 30,
                "expected_text": "연구 보고서", "observed_text": "",
            }],
            "vectors": [],
        },
    )
    assert r["status"] == "FAIL_VISUAL_SLO"
    assert "TEXT_DISAPPEARANCE" in r["defect_codes"]
