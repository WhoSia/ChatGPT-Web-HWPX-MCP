from __future__ import annotations

import hashlib
import json
from typing import Any

from p311_layout_fidelity import adjudicate_layout_fidelity


RECEIPT_SCHEMA = "chatgpt-web-hwpx-mcp/render-receipt/p3.12/v1"


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _finite_nonnegative(value: Any, name: str) -> float:
    number = float(value)
    if number < 0 or number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"{name} must be finite and nonnegative")
    return number


def seal_font_environment(fonts: list[dict]) -> dict:
    normalized = []
    for item in fonts:
        if not isinstance(item, dict):
            raise ValueError("font inventory items must be objects")
        family = str(item.get("family") or item.get("name") or "").strip()
        if not family:
            raise ValueError("font family/name is required")
        normalized.append({
            "family": family,
            "style": str(item.get("style") or "").strip(),
            "postscript_name": str(item.get("postscript_name") or "").strip(),
            "version": str(item.get("version") or "").strip(),
            "file_sha256": str(item.get("file_sha256") or "").lower().strip(),
        })
    normalized.sort(
        key=lambda x: (
            x["family"].casefold(),
            x["style"].casefold(),
            x["postscript_name"].casefold(),
            x["version"],
            x["file_sha256"],
        )
    )
    return {
        "fonts": normalized,
        "font_count": len(normalized),
        "font_inventory_sha256": _sha256(normalized),
        "authority": "FONT_ENVIRONMENT_SEAL",
    }


def validate_capture(capture: dict) -> dict:
    if not isinstance(capture, dict):
        raise ValueError("capture must be an object")

    pages = capture.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError("capture.pages must be a non-empty list")

    page_receipts = []
    total_lines = 0
    for expected_page, page in enumerate(pages):
        if not isinstance(page, dict):
            raise ValueError("page capture must be an object")
        page_index = int(page.get("page_index", expected_page))
        if page_index != expected_page:
            raise ValueError("page indexes must be contiguous from zero")
        width_px = int(page.get("width_px", 0))
        height_px = int(page.get("height_px", 0))
        if width_px <= 0 or height_px <= 0:
            raise ValueError("page width/height must be positive")

        lines = page.get("line_boxes", [])
        if not isinstance(lines, list):
            raise ValueError("line_boxes must be a list")

        normalized_lines = []
        previous_y = -1.0
        for line_index, line in enumerate(lines):
            if not isinstance(line, dict):
                raise ValueError("line box must be an object")
            x = _finite_nonnegative(line.get("x", 0), "line x")
            y = _finite_nonnegative(line.get("y", 0), "line y")
            w = _finite_nonnegative(line.get("width", 0), "line width")
            h = _finite_nonnegative(line.get("height", 0), "line height")
            baseline = _finite_nonnegative(line.get("baseline", y + h), "line baseline")
            if w <= 0 or h <= 0:
                raise ValueError("line width/height must be positive")
            if x + w > width_px + 1e-6 or y + h > height_px + 1e-6:
                raise ValueError("line box exceeds page bounds")
            if y + 1e-6 < previous_y:
                raise ValueError("line boxes must be in nondecreasing vertical order")
            previous_y = y
            normalized_lines.append({
                "line_index": line_index,
                "x": x,
                "y": y,
                "width": w,
                "height": h,
                "baseline": baseline,
                "text_sha256": str(line.get("text_sha256") or ""),
                "paragraph_locator": str(line.get("paragraph_locator") or ""),
            })

        total_lines += len(normalized_lines)
        page_receipts.append({
            "page_index": page_index,
            "width_px": width_px,
            "height_px": height_px,
            "raster_sha256": str(page.get("raster_sha256") or "").lower(),
            "line_boxes": normalized_lines,
            "line_box_sha256": _sha256(normalized_lines),
        })

    return {
        "page_count": len(page_receipts),
        "line_count": total_lines,
        "pages": page_receipts,
        "capture_sha256": _sha256(page_receipts),
        "authority": "PAGINATION_LINE_BOX_CAPTURE",
    }


def normalize_render_receipt(packet: dict) -> dict:
    if not isinstance(packet, dict):
        raise ValueError("render receipt must be an object")
    if packet.get("schema") != RECEIPT_SCHEMA:
        raise ValueError("unsupported render receipt schema")

    fixture_id = str(packet.get("fixture_id") or "").strip()
    source_sha256 = str(packet.get("source_sha256") or "").lower().strip()
    target_sha256 = str(packet.get("target_sha256") or "").lower().strip()
    if not fixture_id or len(source_sha256) != 64 or len(target_sha256) != 64:
        raise ValueError("fixture_id and 64-hex source/target hashes are required")

    renderer = packet.get("renderer") or {}
    name = str(renderer.get("name") or "").strip()
    version = str(renderer.get("version") or "").strip()
    executable_sha256 = str(renderer.get("executable_sha256") or "").lower().strip()
    if not name or not version:
        raise ValueError("renderer name/version are required")

    source_env = seal_font_environment((packet.get("source_environment") or {}).get("fonts", []))
    target_env = seal_font_environment((packet.get("target_environment") or {}).get("fonts", []))
    source_capture = validate_capture(packet.get("source_capture") or {})
    target_capture = validate_capture(packet.get("target_capture") or {})

    metrics = packet.get("metrics") or {}
    calibration = packet.get("calibration") or {}

    normalized = {
        "schema": RECEIPT_SCHEMA,
        "fixture_id": fixture_id,
        "source_sha256": source_sha256,
        "target_sha256": target_sha256,
        "renderer": {
            "name": name,
            "version": version,
            "hancom_native": bool(renderer.get("hancom_native")),
            "executable_sha256": executable_sha256,
            "os": str(renderer.get("os") or ""),
            "dpi": int(renderer.get("dpi", 0) or 0),
            "pdf_backend": str(renderer.get("pdf_backend") or ""),
            "rasterizer": str(renderer.get("rasterizer") or ""),
            "rasterizer_version": str(renderer.get("rasterizer_version") or ""),
        },
        "source_environment": source_env,
        "target_environment": target_env,
        "source_capture": source_capture,
        "target_capture": target_capture,
        "metrics": metrics,
        "calibration": calibration,
    }
    normalized["receipt_sha256"] = _sha256(normalized)
    return normalized


def _line_topology_signature(capture: dict) -> list:
    signature = []
    for page in capture["pages"]:
        lines = page["line_boxes"]
        rich = [
            (
                str(line.get("text_sha256") or ""),
                str(line.get("paragraph_locator") or ""),
            )
            for line in lines
        ]
        if any(text_hash or locator for text_hash, locator in rich):
            signature.append(rich)
        else:
            signature.append(len(lines))
    return signature


def _capture_equal(left: dict, right: dict) -> tuple[bool, bool]:
    pagination_equal = left["page_count"] == right["page_count"]
    line_break_equal = (
        pagination_equal
        and _line_topology_signature(left) == _line_topology_signature(right)
    )
    return pagination_equal, line_break_equal


def adjudicate_fixture_world_contact(
    structural_receipt: dict,
    packet: dict,
) -> dict:
    normalized = normalize_render_receipt(packet)
    pagination_equal, line_break_equal = _capture_equal(
        normalized["source_capture"], normalized["target_capture"]
    )

    supplied = dict(normalized["metrics"])
    if "pagination_equal" in supplied and bool(supplied["pagination_equal"]) != pagination_equal:
        raise ValueError("supplied pagination_equal contradicts captured pages")
    if "line_break_equal" in supplied and bool(supplied["line_break_equal"]) != line_break_equal:
        raise ValueError("supplied line_break_equal contradicts captured line boxes")
    supplied["pagination_equal"] = pagination_equal
    supplied["line_break_equal"] = line_break_equal

    source_font_hash = normalized["source_environment"]["font_inventory_sha256"]
    target_font_hash = normalized["target_environment"]["font_inventory_sha256"]

    render_receipt = {
        "renderer": normalized["renderer"],
        "environment": {
            "font_environment_controlled": bool(
                normalized["source_environment"]["font_count"]
                and normalized["target_environment"]["font_count"]
            ),
            "source_font_inventory_sha256": source_font_hash,
            "target_font_inventory_sha256": target_font_hash,
        },
        "metrics": supplied,
        "calibration": normalized["calibration"],
    }
    adjudication = adjudicate_layout_fidelity(structural_receipt, render_receipt)

    source_rasters = [p["raster_sha256"] for p in normalized["source_capture"]["pages"]]
    target_rasters = [p["raster_sha256"] for p in normalized["target_capture"]["pages"]]
    raster_hashes_present = all(source_rasters) and all(target_rasters)
    raster_hashes_exact = bool(raster_hashes_present and source_rasters == target_rasters)

    if supplied.get("exact_pixel_match") is True and not raster_hashes_exact:
        raise ValueError("exact_pixel_match requires identical page raster hashes")

    world_contact_valid = bool(
        normalized["renderer"]["hancom_native"]
        and normalized["renderer"]["executable_sha256"]
        and normalized["renderer"]["dpi"] > 0
        and raster_hashes_present
    )

    if not world_contact_valid and adjudication["verdict"] == "PIXEL_RENDER_FIDELITY_PASS":
        adjudication["verdict"] = "PIXEL_RENDER_FIDELITY_HOLD"
        adjudication["authority"] = "WORLD_CONTACT_SEAL_INCOMPLETE"
        adjudication["reason_chain"].append("HANCOM_WORLD_CONTACT_SEAL_INCOMPLETE")

    return {
        "fixture_id": normalized["fixture_id"],
        "receipt_sha256": normalized["receipt_sha256"],
        "renderer": normalized["renderer"],
        "font_seal": {
            "source": source_font_hash,
            "target": target_font_hash,
            "exact": source_font_hash == target_font_hash,
        },
        "pagination": {
            "source_pages": normalized["source_capture"]["page_count"],
            "target_pages": normalized["target_capture"]["page_count"],
            "exact": pagination_equal,
        },
        "line_boxes": {
            "source_lines": normalized["source_capture"]["line_count"],
            "target_lines": normalized["target_capture"]["line_count"],
            "topology_exact": line_break_equal,
        },
        "raster": {
            "hashes_present": raster_hashes_present,
            "exact_hashes": raster_hashes_exact,
        },
        "world_contact_valid": world_contact_valid,
        "adjudication": adjudication,
        "authority": "FIXTURE_LEVEL_HANCOM_RENDER_WORLD_CONTACT_RECEIPT",
    }


def adjudicate_fixture_set(structural_receipts: dict[str, dict], packets: list[dict]) -> dict:
    if not packets:
        raise ValueError("at least one fixture packet is required")
    seen = set()
    fixtures = []
    for packet in packets:
        fixture_id = str(packet.get("fixture_id") or "")
        if fixture_id in seen:
            raise ValueError("duplicate fixture_id")
        seen.add(fixture_id)
        if fixture_id not in structural_receipts:
            raise ValueError(f"missing structural receipt for fixture {fixture_id}")
        fixtures.append(
            adjudicate_fixture_world_contact(structural_receipts[fixture_id], packet)
        )

    exact_pass = [
        item for item in fixtures
        if item["adjudication"]["verdict"] == "PIXEL_RENDER_FIDELITY_PASS"
    ]
    calibrated_pass = [
        item for item in fixtures
        if item["adjudication"]["verdict"].startswith("RENDERER_NORMALIZED_FIDELITY_PASS")
    ]
    holds = [
        item for item in fixtures
        if "PIXEL_RENDER_FIDELITY_HOLD" in item["adjudication"]["verdict"]
    ]
    return {
        "fixture_count": len(fixtures),
        "exact_pixel_pass_count": len(exact_pass),
        "calibrated_render_pass_count": len(calibrated_pass),
        "hold_count": len(holds),
        "all_world_contact_valid": all(item["world_contact_valid"] for item in fixtures),
        "all_exact_pixel": len(exact_pass) == len(fixtures),
        "fixtures": fixtures,
        "set_receipt_sha256": _sha256([
            {"fixture_id": item["fixture_id"], "receipt_sha256": item["receipt_sha256"]}
            for item in fixtures
        ]),
        "authority": (
            "FIXTURE_SET_EXACT_PIXEL_AUTHORITY"
            if len(exact_pass) == len(fixtures)
            else "FIXTURE_SET_CALIBRATED_OR_HOLD_AUTHORITY"
        ),
    }
