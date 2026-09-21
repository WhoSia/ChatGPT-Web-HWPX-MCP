from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from p315_cross_version import normalize_font_file_custody


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def find_predecessor(pack: Path, family: str, selected_magnitude: float) -> dict:
    candidates = []
    for receipt_path in sorted((pack / "calibration").glob(f"{family}-*/capture/render-receipt.json")):
        receipt = load_json(receipt_path)
        metrics = receipt.get("metrics") or {}
        name = receipt_path.parents[1].name
        suffix = int(name.split("-", 1)[1])
        magnitude = float(suffix - 10000 if family == "advance" else suffix)
        candidates.append({
            "candidate_id": name,
            "magnitude": magnitude,
            "line_break_equal": metrics.get("line_break_equal") is True,
        })
    smaller = [item for item in candidates if item["magnitude"] < selected_magnitude]
    if not smaller:
        raise ValueError(f"no predecessor candidate for {family}")
    return sorted(smaller, key=lambda x: x["magnitude"])[-1]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--pack", required=True)
    p.add_argument("--font-before", required=True)
    p.add_argument("--font-after", required=True)
    p.add_argument("--session-id", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    pack = Path(args.pack)
    summary = load_json(pack / "windows-hancom-run-summary.json")
    boundary = load_json(pack / "boundary-selection.json")
    manifest_path = pack / "capture-ready-manifest.json"
    baseline_receipt = load_json(pack / "near-wrap-base" / "capture" / "render-receipt.json")

    before = normalize_font_file_custody(load_json(Path(args.font_before)))
    after = normalize_font_file_custody(load_json(Path(args.font_after)))
    if before["font_file_custody_sha256"] != after["font_file_custody_sha256"]:
        raise ValueError("font-file custody changed during capture session")

    advance_selected = (boundary.get("advance") or {}).get("selected")
    frame_selected = (boundary.get("frame") or {}).get("selected")
    if not advance_selected or not frame_selected:
        raise ValueError("capture pack is not boundary-ready")

    advance_pred = find_predecessor(pack, "advance", float(advance_selected["magnitude"]))
    frame_pred = find_predecessor(pack, "frame", float(frame_selected["magnitude"]))

    metrics = baseline_receipt.get("metrics") or {}
    source_pages = (baseline_receipt.get("source_capture") or {}).get("pages") or []
    target_pages = (baseline_receipt.get("target_capture") or {}).get("pages") or []
    if not source_pages or not target_pages:
        raise ValueError("baseline raster pages missing")

    failed = summary.get("failed") or []
    succeeded = summary.get("succeeded") or []
    skipped = summary.get("skipped") or []
    world_contact_pass = bool(
        not failed
        and bool(summary.get("boundary_ready"))
        and metrics.get("pagination_equal") is True
        and metrics.get("line_break_equal") is True
        and metrics.get("exact_pixel_match") is True
        and float(metrics.get("pixel_diff_ratio", 1.0)) == 0.0
        and advance_pred["line_break_equal"] is True
        and advance_selected.get("line_break_diverged") is True
        and frame_pred["line_break_equal"] is True
        and frame_selected.get("line_break_diverged") is True
    )

    renderer = baseline_receipt.get("renderer") or {}
    custody_raw = load_json(Path(args.font_before))
    session = {
        "schema": "chatgpt-web-hwpx-mcp/cross-version-session/p3.15/v1",
        "session_id": args.session_id,
        "world_contact_pass": world_contact_pass,
        "baseline_exact_pixel_pass": bool(metrics.get("exact_pixel_match")),
        "positive_sensitivity_pass": bool(
            advance_selected.get("line_break_diverged") is True
            and frame_selected.get("line_break_diverged") is True
        ),
        "renderer_version": str(summary.get("hancom_version") or renderer.get("version") or ""),
        "renderer_executable_sha256": str(
            summary.get("hancom_executable_sha256") or renderer.get("executable_sha256") or ""
        ).lower(),
        "os_name": str(custody_raw.get("os_name") or ""),
        "os_version": str(custody_raw.get("os_version") or ""),
        "machine_id": str(custody_raw.get("machine_id") or ""),
        "locale": str(custody_raw.get("locale") or ""),
        "dpi": int(summary.get("dpi") or renderer.get("dpi") or 0),
        "rasterizer": str(renderer.get("rasterizer") or ""),
        "rasterizer_version": str(renderer.get("rasterizer_version") or ""),
        "fixture_set_sha256": sha256_file(manifest_path),
        "font_file_custody_sha256": before["font_file_custody_sha256"],
        "font_file_count": before["file_count"],
        "font_custody_before_sha256": sha256_file(Path(args.font_before)),
        "font_custody_after_sha256": sha256_file(Path(args.font_after)),
        "baseline_source_raster_sha256": str(source_pages[0].get("raster_sha256") or ""),
        "baseline_target_raster_sha256": str(target_pages[0].get("raster_sha256") or ""),
        "boundaries": {
            "advance": {
                "candidate_id": str(advance_selected["candidate_id"]),
                "magnitude": float(advance_selected["magnitude"]),
                "predecessor_candidate_id": advance_pred["candidate_id"],
                "predecessor_line_break_equal": advance_pred["line_break_equal"],
                "selected_line_break_equal": False,
            },
            "frame": {
                "candidate_id": str(frame_selected["candidate_id"]),
                "magnitude": float(frame_selected["magnitude"]),
                "predecessor_candidate_id": frame_pred["candidate_id"],
                "predecessor_line_break_equal": frame_pred["line_break_equal"],
                "selected_line_break_equal": False,
            },
        },
        "execution": {
            "succeeded": len(succeeded),
            "skipped": len(skipped),
            "failed": len(failed),
            "boundary_ready": bool(summary.get("boundary_ready")),
        },
        "authority": (
            "P3_15_CUSTODIED_HANCOM_REPLAY_SESSION"
            if world_contact_pass else "P3_15_REPLAY_SESSION_HOLD"
        ),
    }
    session["session_sha256"] = hashlib.sha256(
        json.dumps(session, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(session, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "session_id": session["session_id"],
        "world_contact_pass": session["world_contact_pass"],
        "renderer_version": session["renderer_version"],
        "font_file_custody_sha256": session["font_file_custody_sha256"],
        "session_sha256": session["session_sha256"],
        "out": str(out),
    }, ensure_ascii=False, indent=2))
    return 0 if world_contact_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
