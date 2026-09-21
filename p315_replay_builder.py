from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from p315_cross_version import (
    SCHEMA,
    adjudicate_cross_version_replay,
    normalize_font_file_custody,
)


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _fixture_set_sha256(manifest: dict) -> str:
    rows = []
    for item in manifest.get("fixtures", []):
        rows.append((item["fixture_id"], item["source_sha256"], item["target_sha256"]))
    for family in ("advance", "frame"):
        for item in (manifest.get("boundary_calibration_ladder") or {}).get(family, []):
            rows.append((item["candidate_id"], item["source_sha256"], item["target_sha256"]))
    return _sha(sorted(rows))


def _boundary_record(pack: Path, manifest: dict, selection: dict, family: str) -> dict:
    selected = (selection.get(family) or {}).get("selected")
    if not selected:
        raise ValueError(f"{family} boundary not selected")
    ladder = (manifest.get("boundary_calibration_ladder") or {}).get(family, [])
    ids = [item["candidate_id"] for item in sorted(ladder, key=lambda x: float(x["magnitude"]))]
    try:
        index = ids.index(selected["candidate_id"])
    except ValueError as exc:
        raise ValueError(f"selected {family} candidate missing from manifest") from exc
    if index == 0:
        raise ValueError(f"{family} selected boundary has no predecessor")
    predecessor_id = ids[index - 1]

    selected_receipt = _load(pack / "calibration" / selected["candidate_id"] / "capture" / "render-receipt.json")
    predecessor_receipt = _load(pack / "calibration" / predecessor_id / "capture" / "render-receipt.json")

    return {
        "candidate_id": selected["candidate_id"],
        "magnitude": float(selected["magnitude"]),
        "predecessor_candidate_id": predecessor_id,
        "predecessor_line_break_equal": predecessor_receipt["metrics"]["line_break_equal"] is True,
        "selected_line_break_equal": selected_receipt["metrics"]["line_break_equal"] is True,
        "selected_pixel_diff_ratio": float(selected_receipt["metrics"]["pixel_diff_ratio"]),
    }


def build_version_record(pack_dir: Path, font_custody_path: Path) -> dict:
    pack = Path(pack_dir)
    manifest = _load(pack / "capture-ready-manifest.json")
    summary = _load(pack / "windows-hancom-run-summary.json")
    selection = _load(pack / "boundary-selection.json")
    baseline = _load(pack / "near-wrap-base" / "capture" / "render-receipt.json")
    font_custody = normalize_font_file_custody(_load(Path(font_custody_path)))

    failed = summary.get("failed") or []
    succeeded = summary.get("succeeded") or []
    skipped = summary.get("skipped") or []
    expected = 19
    completed = len(succeeded) + len(skipped)

    baseline_metrics = baseline.get("metrics") or {}
    source_pages = (baseline.get("source_capture") or {}).get("pages") or []
    target_pages = (baseline.get("target_capture") or {}).get("pages") or []
    if not source_pages or not target_pages:
        raise ValueError("baseline capture pages missing")

    advance = _boundary_record(pack, manifest, selection, "advance")
    frame = _boundary_record(pack, manifest, selection, "frame")
    sensitivity = bool(
        advance["predecessor_line_break_equal"]
        and advance["selected_line_break_equal"] is False
        and frame["predecessor_line_break_equal"]
        and frame["selected_line_break_equal"] is False
    )
    baseline_exact = bool(
        baseline_metrics.get("pagination_equal") is True
        and baseline_metrics.get("line_break_equal") is True
        and baseline_metrics.get("exact_pixel_match") is True
        and float(baseline_metrics.get("pixel_diff_ratio", 1)) == 0
        and float(baseline_metrics.get("mae", 1)) == 0
    )
    world_contact = bool(
        completed == expected
        and not failed
        and summary.get("boundary_ready") is True
        and baseline_exact
        and sensitivity
    )

    return {
        "world_contact_pass": world_contact,
        "baseline_exact_pixel_pass": baseline_exact,
        "positive_sensitivity_pass": sensitivity,
        "renderer_version": str(summary.get("hancom_version") or ""),
        "renderer_executable_sha256": str(summary.get("hancom_executable_sha256") or "").lower(),
        "os_name": font_custody.get("os_name", "") or (_load(Path(font_custody_path)).get("os_name") or ""),
        "os_version": _load(Path(font_custody_path)).get("os_version") or "",
        "machine_id": _load(Path(font_custody_path)).get("machine_id") or "",
        "locale": _load(Path(font_custody_path)).get("locale") or "",
        "dpi": int(summary.get("dpi", baseline.get("renderer", {}).get("dpi", 0)) or 0),
        "rasterizer": str((baseline.get("renderer") or {}).get("rasterizer") or ""),
        "rasterizer_version": str((baseline.get("renderer") or {}).get("rasterizer_version") or ""),
        "fixture_set_sha256": _fixture_set_sha256(manifest),
        "font_file_custody_sha256": font_custody["font_file_custody_sha256"],
        "font_file_count": font_custody["file_count"],
        "baseline_source_raster_sha256": str(source_pages[0].get("raster_sha256") or ""),
        "baseline_target_raster_sha256": str(target_pages[0].get("raster_sha256") or ""),
        "boundaries": {
            "advance": advance,
            "frame": frame,
        },
    }


def build_cross_version_packet(
    first_pack: Path,
    first_font_custody: Path,
    second_pack: Path,
    second_font_custody: Path,
) -> dict:
    first = build_version_record(first_pack, first_font_custody)
    second = build_version_record(second_pack, second_font_custody)
    packet = {
        "schema": SCHEMA,
        "versions": [first, second],
    }
    packet["packet_sha256"] = _sha(packet)
    packet["adjudication"] = adjudicate_cross_version_replay(packet)
    return packet
