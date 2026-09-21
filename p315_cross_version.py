from __future__ import annotations

import hashlib
import json
from typing import Any


SCHEMA = "chatgpt-web-hwpx-mcp/cross-version-replay/p3.15/v1"


def _canon(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canon(value)).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _font_file_digest(files: list[dict]) -> str:
    lines = [
        f"{item['registry_name']}\0{item['path']}\0{item['sha256']}\0{item['bytes']}"
        for item in files
    ]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def normalize_font_file_custody(receipt: dict) -> dict:
    if not isinstance(receipt, dict):
        raise ValueError("font custody receipt must be an object")
    if receipt.get("schema") != "chatgpt-web-hwpx-mcp/font-file-custody/p3.15/v1":
        raise ValueError("unsupported font custody schema")
    files = receipt.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("font custody must contain at least one file")
    normalized = []
    for item in files:
        path = str(item.get("path") or "").strip()
        sha256 = str(item.get("sha256") or "").strip().lower()
        size = int(item.get("bytes", 0) or 0)
        if not path:
            raise ValueError("font file path missing")
        if len(sha256) != 64 or any(ch not in "0123456789abcdef" for ch in sha256):
            raise ValueError("font file hash must be lowercase SHA-256")
        if size <= 0:
            raise ValueError("font file size must be positive")
        normalized.append({
            "registry_name": str(item.get("registry_name") or ""),
            "path": path,
            "sha256": sha256,
            "bytes": size,
        })
    normalized.sort(key=lambda x: (x["registry_name"].casefold(), x["path"].casefold(), x["sha256"]))
    digest = _font_file_digest(normalized)
    claimed = str(receipt.get("font_file_custody_sha256") or "").strip().lower()
    if claimed and claimed != digest:
        raise ValueError("font custody digest mismatch")
    return {
        "files": normalized,
        "file_count": len(normalized),
        "font_file_custody_sha256": digest,
        "authority": "WINDOWS_FONT_FILE_CRYPTOGRAPHIC_CUSTODY",
    }


def isolate_environment_delta(first: dict, second: dict) -> dict:
    keys = (
        "os_name",
        "os_version",
        "machine_id",
        "locale",
        "dpi",
        "rasterizer",
        "rasterizer_version",
        "fixture_set_sha256",
        "font_file_custody_sha256",
    )
    deltas = {}
    for key in keys:
        a = first.get(key)
        b = second.get(key)
        if a != b:
            deltas[key] = {"first": a, "second": b}
    renderer_only = set(deltas).issubset({"os_version"}) and (
        first.get("fixture_set_sha256") == second.get("fixture_set_sha256")
        and first.get("font_file_custody_sha256") == second.get("font_file_custody_sha256")
        and first.get("dpi") == second.get("dpi")
        and first.get("rasterizer") == second.get("rasterizer")
        and first.get("rasterizer_version") == second.get("rasterizer_version")
    )
    if not deltas:
        authority = "ENVIRONMENT_EXACT_MATCH"
    elif renderer_only:
        authority = "ENVIRONMENT_RENDERER_VERSION_ISOLATED"
    else:
        authority = "ENVIRONMENT_DELTA_PRESENT"
    return {
        "delta_fields": deltas,
        "delta_count": len(deltas),
        "renderer_version_isolated": renderer_only or not deltas,
        "authority": authority,
    }


def _boundary(record: dict, family: str) -> dict:
    item = (record.get("boundaries") or {}).get(family) or {}
    _require(item.get("predecessor_line_break_equal") is True, f"{family} predecessor must be equal")
    _require(item.get("selected_line_break_equal") is False, f"{family} selected candidate must diverge")
    magnitude = float(item.get("magnitude", 0) or 0)
    _require(magnitude > 0, f"{family} boundary magnitude must be positive")
    return {
        "candidate_id": str(item.get("candidate_id") or ""),
        "magnitude": magnitude,
        "predecessor_candidate_id": str(item.get("predecessor_candidate_id") or ""),
    }


def adjudicate_cross_version_replay(packet: dict) -> dict:
    if not isinstance(packet, dict) or packet.get("schema") != SCHEMA:
        raise ValueError("unsupported P3.15 replay schema")
    versions = packet.get("versions")
    if not isinstance(versions, list) or len(versions) != 2:
        raise ValueError("P3.15 requires exactly two version records")

    first, second = versions
    for label, item in (("first", first), ("second", second)):
        _require(item.get("world_contact_pass") is True, f"{label} world-contact must pass")
        _require(item.get("baseline_exact_pixel_pass") is True, f"{label} baseline exact-pixel must pass")
        _require(item.get("positive_sensitivity_pass") is True, f"{label} sensitivity must pass")
        _require(bool(item.get("renderer_version")), f"{label} renderer version missing")
        _require(bool(item.get("renderer_executable_sha256")), f"{label} renderer executable hash missing")
        _require(bool(item.get("fixture_set_sha256")), f"{label} fixture-set hash missing")
        _require(bool(item.get("font_file_custody_sha256")), f"{label} font custody missing")

    distinct_versions = first["renderer_version"] != second["renderer_version"]
    distinct_executables = first["renderer_executable_sha256"] != second["renderer_executable_sha256"]
    same_fixture_set = first["fixture_set_sha256"] == second["fixture_set_sha256"]
    same_fonts = first["font_file_custody_sha256"] == second["font_file_custody_sha256"]
    environment = isolate_environment_delta(first, second)

    first_advance = _boundary(first, "advance")
    second_advance = _boundary(second, "advance")
    first_frame = _boundary(first, "frame")
    second_frame = _boundary(second, "frame")

    transport = {
        "advance": {
            "first": first_advance,
            "second": second_advance,
            "magnitude_shift": second_advance["magnitude"] - first_advance["magnitude"],
            "same_selected_boundary": first_advance["candidate_id"] == second_advance["candidate_id"],
        },
        "frame": {
            "first": first_frame,
            "second": second_frame,
            "magnitude_shift": second_frame["magnitude"] - first_frame["magnitude"],
            "same_selected_boundary": first_frame["candidate_id"] == second_frame["candidate_id"],
        },
    }

    cross_version_baseline_pixel_stable = bool(
        first.get("baseline_source_raster_sha256")
        and first.get("baseline_source_raster_sha256") == second.get("baseline_source_raster_sha256")
        and first.get("baseline_target_raster_sha256")
        and first.get("baseline_target_raster_sha256") == second.get("baseline_target_raster_sha256")
    )

    replay_ready = bool(
        distinct_versions
        and distinct_executables
        and same_fixture_set
        and same_fonts
        and environment["renderer_version_isolated"]
    )

    if replay_ready and cross_version_baseline_pixel_stable:
        verdict = "CROSS_VERSION_NATIVE_PIXEL_STABILITY_PROMOTION_CANDIDATE"
        authority = "CROSS_VERSION_NATIVE_PIXEL_STABILITY_REOPENED"
    elif replay_ready:
        verdict = "VERSION_INDEXED_PIXEL_FIDELITY_PROMOTION_CANDIDATE"
        authority = "CROSS_VERSION_VERSION_INDEXED_PROMOTION_REOPENED"
    else:
        verdict = "CROSS_VERSION_PIXEL_FIDELITY_HOLD"
        authority = "CROSS_VERSION_REPLAY_HOLD"

    result = {
        "distinct_versions": distinct_versions,
        "distinct_renderer_executables": distinct_executables,
        "same_fixture_set": same_fixture_set,
        "same_font_file_custody": same_fonts,
        "environment_delta": environment,
        "boundary_transport": transport,
        "cross_version_baseline_pixel_stable": cross_version_baseline_pixel_stable,
        "promotion_reopened": replay_ready,
        "verdict": verdict,
        "authority": authority,
    }
    result["adjudication_sha256"] = _sha(result)
    return result
