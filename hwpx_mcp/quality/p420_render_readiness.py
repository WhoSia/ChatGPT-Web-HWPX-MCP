"""P4.20 structured-render readiness; never forge native visual authority.

A valid HWPX ZIP is not visual evidence. Native page captures must originate
from an independent trusted renderer and require separate host attestation.
This evaluator reports preliminary defects, not a production certification.
"""
from __future__ import annotations

import re
from typing import Any

from hwpx_mcp.custody.p312_render_harness import validate_capture
from hwpx_mcp.rendering.p411_visual_oracle import (
    detect_native_visual_defects, evaluate_visual_slo,
)

SHA256 = re.compile(r"^[0-9a-f]{64}$")
STRICT_VISUAL_POLICY = {
    "schema": "chatgpt-web-hwpx-mcp/p420/visual-hard-zero/v1",
    "mode": "FAIL_CLOSED",
    "hard_zero": [
        "VECTOR_ESCAPE", "REGION_CLIP", "TEXT_DISAPPEARANCE",
        "LABEL_VALUE_DETACHMENT", "KPI_CONTAINER_COLLAPSE",
        "OBJECT_OVERLAP", "ALIGNMENT_DRIFT",
    ],
}


def assess_render_readiness(
    *, artifact_sha256: str, structural_valid: bool,
    capture: dict[str, Any] | None = None,
    observation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return HOLD without world evidence and FAIL on observed hard defects.

    Even a clean untrusted observation cannot prove real Hancom capture,
    image authenticity or final approval. An independent attested native
    capture and human/visual review are still needed to promote a release.
    """
    if not isinstance(artifact_sha256, str) or not SHA256.fullmatch(artifact_sha256):
        raise ValueError("artifact_sha256 must be a lowercase 64-hex digest")
    if not structural_valid:
        return {"status": "FAIL_STRUCTURE", "release_eligible": False,
                "authority": "P420_PRELIMINARY_STATIC_GATE"}
    if capture is None or observation is None:
        return {"status": "HOLD_NATIVE_CAPTURE", "release_eligible": False,
                "authority": "P420_PRELIMINARY_STATIC_GATE"}
    if not isinstance(capture, dict) or not isinstance(observation, dict):
        raise ValueError("capture and observation must be objects")
    if capture.get("source_sha256") != artifact_sha256:
        return {"status": "FAIL_SOURCE_BINDING", "release_eligible": False,
                "authority": "P420_PRELIMINARY_CAPTURE_GATE"}
    pages = validate_capture({"pages": capture.get("pages")})
    if any(not SHA256.fullmatch(str(page["raster_sha256"])) for page in pages["pages"]):
        return {"status": "HOLD_RASTER_PROVENANCE", "release_eligible": False,
                "authority": "P420_PRELIMINARY_CAPTURE_GATE"}
    if capture.get("renderer") != "Hancom Hangul" or not capture.get("renderer_version"):
        return {"status": "HOLD_RENDERER_IDENTITY", "release_eligible": False,
                "authority": "P420_PRELIMINARY_CAPTURE_GATE"}
    if len(pages["pages"]) != int(observation.get("page_count", -1)):
        return {"status": "FAIL_PAGE_COUNT_BINDING", "release_eligible": False,
                "authority": "P420_PRELIMINARY_CAPTURE_GATE"}
    defects = detect_native_visual_defects(observation)
    slo = evaluate_visual_slo(defects, policy=STRICT_VISUAL_POLICY)
    return {
        "status": "FAIL_VISUAL_SLO" if slo["status"] == "FAIL" else "HOLD_INDEPENDENT_NATIVE_ATTESTATION",
        "release_eligible": False,
        "defect_codes": sorted({issue["code"] for issue in defects["issues"]}),
        "capture_sha256": pages["capture_sha256"],
        "visual_slo_sha256": slo["visual_slo_sha256"],
        "authority": "P420_UNATTESTED_VISUAL_EVIDENCE_ASSESSMENT",
    }
