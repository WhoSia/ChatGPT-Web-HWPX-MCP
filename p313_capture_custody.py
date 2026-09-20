from __future__ import annotations

import hashlib
import json
from typing import Any

from p312_render_harness import adjudicate_fixture_world_contact


CAPTURE_SCHEMA = "chatgpt-web-hwpx-mcp/capture-bundle/p3.13/v1"
RUNNER_SCHEMA = "chatgpt-web-hwpx-mcp/windows-hancom-runner/p3.13/v1"


def _canon(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canon(value)).hexdigest()


def _hex64(value: Any, name: str, allow_empty: bool = False) -> str:
    text = str(value or "").lower().strip()
    if allow_empty and not text:
        return ""
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"{name} must be a 64-character lowercase hex SHA-256")
    return text


def validate_runner_identity(runner: dict) -> dict:
    if not isinstance(runner, dict) or runner.get("schema") != RUNNER_SCHEMA:
        raise ValueError("unsupported runner identity schema")
    os_name = str(runner.get("os") or "").strip()
    os_version = str(runner.get("os_version") or "").strip()
    machine_id = str(runner.get("machine_id") or "").strip()
    hancom_version = str(runner.get("hancom_version") or "").strip()
    hancom_exe_sha = _hex64(runner.get("hancom_executable_sha256"), "hancom executable hash")
    harness_sha = _hex64(runner.get("harness_sha256"), "harness hash")
    if "windows" not in os_name.casefold():
        raise ValueError("trusted P3.13 runner must be Windows")
    if not os_version or not machine_id or not hancom_version:
        raise ValueError("runner OS version, machine_id and Hancom version are required")
    canonical = {
        "schema": RUNNER_SCHEMA,
        "os": os_name,
        "os_version": os_version,
        "machine_id": machine_id,
        "hancom_version": hancom_version,
        "hancom_executable_sha256": hancom_exe_sha,
        "harness_sha256": harness_sha,
        "capture_user": str(runner.get("capture_user") or ""),
        "locale": str(runner.get("locale") or ""),
        "display_scale_percent": int(runner.get("display_scale_percent", 100) or 100),
    }
    canonical["runner_identity_sha256"] = _sha(canonical)
    return canonical


def validate_artifact_custody(bundle: dict) -> dict:
    if not isinstance(bundle, dict) or bundle.get("schema") != CAPTURE_SCHEMA:
        raise ValueError("unsupported capture bundle schema")
    runner = validate_runner_identity(bundle.get("runner") or {})
    artifacts = bundle.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("capture bundle must contain artifacts")

    normalized = []
    seen_paths = set()
    for index, item in enumerate(artifacts):
        if not isinstance(item, dict):
            raise ValueError("artifact entry must be an object")
        path = str(item.get("path") or "").replace("\\", "/").strip()
        if not path or path.startswith("/") or ".." in path.split("/"):
            raise ValueError("artifact path must be safe and relative")
        if path in seen_paths:
            raise ValueError("duplicate artifact path")
        seen_paths.add(path)
        sha = _hex64(item.get("sha256"), f"artifact[{index}] hash")
        size = int(item.get("bytes", 0) or 0)
        if size <= 0:
            raise ValueError("artifact bytes must be positive")
        role = str(item.get("role") or "").strip()
        if role not in {
            "source-document", "target-document", "source-pdf", "target-pdf",
            "source-raster", "target-raster", "line-box-capture",
            "font-inventory", "runner-log", "render-receipt",
        }:
            raise ValueError(f"unsupported artifact role: {role}")
        normalized.append({
            "path": path,
            "sha256": sha,
            "bytes": size,
            "role": role,
        })

    normalized.sort(key=lambda x: (x["role"], x["path"]))
    required_roles = {
        "source-document", "target-document",
        "source-raster", "target-raster",
        "line-box-capture", "font-inventory", "render-receipt",
    }
    roles = {item["role"] for item in normalized}
    missing = sorted(required_roles - roles)
    if missing:
        raise ValueError(f"capture bundle missing required roles: {missing}")

    previous = _hex64(bundle.get("previous_bundle_sha256"), "previous bundle hash", allow_empty=True)
    canonical = {
        "schema": CAPTURE_SCHEMA,
        "fixture_id": str(bundle.get("fixture_id") or "").strip(),
        "runner": runner,
        "artifacts": normalized,
        "previous_bundle_sha256": previous,
        "captured_at": str(bundle.get("captured_at") or "").strip(),
    }
    if not canonical["fixture_id"] or not canonical["captured_at"]:
        raise ValueError("fixture_id and captured_at are required")
    canonical["bundle_sha256"] = _sha(canonical)
    canonical["custody_complete"] = True
    canonical["authority"] = "ARTIFACT_CUSTODY_CHAIN_RECEIPT"
    return canonical


def verify_custody_chain(bundles: list[dict]) -> dict:
    if not bundles:
        raise ValueError("custody chain requires at least one bundle")
    normalized = [validate_artifact_custody(item) for item in bundles]
    for index, current in enumerate(normalized):
        expected_previous = "" if index == 0 else normalized[index - 1]["bundle_sha256"]
        if current["previous_bundle_sha256"] != expected_previous:
            raise ValueError(f"custody chain break at index {index}")
    return {
        "bundle_count": len(normalized),
        "head_sha256": normalized[-1]["bundle_sha256"],
        "runner_identities": sorted({
            item["runner"]["runner_identity_sha256"] for item in normalized
        }),
        "chain_valid": True,
        "authority": "APPEND_ONLY_CAPTURE_CUSTODY_CHAIN",
    }


def near_wrap_positive_sensitivity_spec() -> dict:
    fixtures = [
        {
            "fixture_id": "near-wrap-base",
            "purpose": "control paragraph positioned within one glyph advance of wrap boundary",
            "perturbation": "none",
            "expected_relation": "baseline",
        },
        {
            "fixture_id": "near-wrap-plus-advance",
            "purpose": "positive sensitivity control",
            "perturbation": "increase one run advance or effective width enough to force exactly one soft-wrap transition",
            "expected_relation": "line_break_must_diverge",
        },
        {
            "fixture_id": "near-wrap-minus-frame",
            "purpose": "independent positive sensitivity control",
            "perturbation": "reduce effective text-frame width enough to force one soft-wrap transition",
            "expected_relation": "line_break_must_diverge",
        },
    ]
    return {
        "fixtures": fixtures,
        "required_positive_controls": 2,
        "authority": "NEAR_WRAP_POSITIVE_SENSITIVITY_CORPUS_SPEC",
        "spec_sha256": _sha(fixtures),
    }


def adjudicate_sensitivity_controls(results: dict[str, dict]) -> dict:
    required = ("near-wrap-base", "near-wrap-plus-advance", "near-wrap-minus-frame")
    missing = [key for key in required if key not in results]
    if missing:
        raise ValueError(f"missing sensitivity results: {missing}")

    base = results["near-wrap-base"]
    plus = results["near-wrap-plus-advance"]
    minus = results["near-wrap-minus-frame"]

    base_ok = base.get("adjudication", {}).get("promotion_gate", {}).get("line_break_exact") is True
    plus_detected = plus.get("adjudication", {}).get("promotion_gate", {}).get("line_break_exact") is False
    minus_detected = minus.get("adjudication", {}).get("promotion_gate", {}).get("line_break_exact") is False

    pass_controls = bool(base_ok and plus_detected and minus_detected)
    return {
        "base_stable": base_ok,
        "plus_advance_detected": plus_detected,
        "minus_frame_detected": minus_detected,
        "positive_sensitivity_pass": pass_controls,
        "authority": (
            "POSITIVE_SENSITIVITY_CERTIFIED"
            if pass_controls else "POSITIVE_SENSITIVITY_HOLD"
        ),
    }


def adjudicate_cross_version_replay(
    structural_receipt: dict,
    trials: list[dict],
    sensitivity: dict | None = None,
) -> dict:
    if len(trials) < 2:
        raise ValueError("cross-version replay requires at least two Hancom trials")
    receipts = [adjudicate_fixture_world_contact(structural_receipt, item) for item in trials]
    versions = [item["renderer"]["version"] for item in receipts]
    if len(set(versions)) < 2:
        raise ValueError("cross-version replay requires distinct Hancom versions")

    exact = [
        item["adjudication"]["verdict"] == "PIXEL_RENDER_FIDELITY_PASS"
        for item in receipts
    ]
    calibrated_or_exact = [
        item["adjudication"]["verdict"] == "PIXEL_RENDER_FIDELITY_PASS"
        or item["adjudication"]["verdict"].startswith("RENDERER_NORMALIZED_FIDELITY_PASS")
        for item in receipts
    ]
    all_world_contact = all(item["world_contact_valid"] for item in receipts)
    sensitivity_ok = bool(
        sensitivity and sensitivity.get("positive_sensitivity_pass") is True
    )

    if all_world_contact and all(exact) and sensitivity_ok:
        verdict = "CROSS_VERSION_EXACT_PIXEL_PROMOTION_CANDIDATE"
    elif all_world_contact and all(calibrated_or_exact) and sensitivity_ok:
        verdict = "CROSS_VERSION_CALIBRATED_RENDER_AUTHORITY"
    else:
        verdict = "CROSS_VERSION_PIXEL_FIDELITY_HOLD"

    return {
        "trial_count": len(receipts),
        "versions": versions,
        "all_world_contact_valid": all_world_contact,
        "all_exact_pixel": all(exact),
        "all_calibrated_or_exact": all(calibrated_or_exact),
        "positive_sensitivity_pass": sensitivity_ok,
        "verdict": verdict,
        "receipts": receipts,
        "replay_sha256": _sha([
            {
                "fixture_id": item["fixture_id"],
                "receipt_sha256": item["receipt_sha256"],
                "version": item["renderer"]["version"],
                "verdict": item["adjudication"]["verdict"],
            }
            for item in receipts
        ]),
        "authority": "CROSS_VERSION_HANCOM_REPLAY_ADJUDICATION",
    }
