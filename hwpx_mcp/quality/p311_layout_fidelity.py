from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

from lxml import etree

HP_URI = "http://www.hancom.co.kr/hwpml/2011/paragraph"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _sha256_json(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _section_names(archive: zipfile.ZipFile) -> list[str]:
    names = [
        name for name in archive.namelist()
        if name.startswith("Contents/section") and name.endswith(".xml")
    ]
    return sorted(
        names,
        key=lambda name: _int(
            name.rsplit("section", 1)[-1].split(".xml", 1)[0], 10**9
        ),
    )


def build_hwpx_layout_receipt(path: Path) -> dict:
    """Extract renderer-independent page/section and hard-break evidence.

    This is deliberately not a renderer oracle. Soft wraps, glyph advances,
    pagination and raster placement require external render world contact.
    """
    sections: list[dict] = []
    font_faces: list[dict] = []
    hard_line_breaks = 0
    explicit_page_breaks = 0
    explicit_column_breaks = 0
    paragraph_count = 0

    with zipfile.ZipFile(path, "r") as archive:
        if "Contents/header.xml" in archive.namelist():
            root = etree.fromstring(archive.read("Contents/header.xml"))
            for node in root.iter():
                if _local(node.tag) not in {"fontface", "font"}:
                    continue
                attrs = dict(node.attrib)
                if not attrs:
                    continue
                font_faces.append({
                    "name": attrs.get("name") or attrs.get("face") or attrs.get("fontName"),
                    "lang": attrs.get("lang") or attrs.get("langID"),
                    "type": attrs.get("type"),
                })

        for section_index, section_name in enumerate(_section_names(archive)):
            root = etree.fromstring(archive.read(section_name))
            page_pr = None
            margin = None
            for node in root.iter():
                local = _local(node.tag)
                if page_pr is None and local == "pagePr":
                    page_pr = node
                elif margin is None and local in {"margin", "pageMargin"}:
                    margin = node
                if local == "p":
                    paragraph_count += 1
                    if str(node.get("pageBreak", "0")).lower() in {"1", "true"}:
                        explicit_page_breaks += 1
                    if str(node.get("columnBreak", "0")).lower() in {"1", "true"}:
                        explicit_column_breaks += 1
                elif local == "lineBreak":
                    hard_line_breaks += 1

            pa = {} if page_pr is None else dict(page_pr.attrib)
            ma = {} if margin is None else dict(margin.attrib)
            width = _int(pa.get("width"))
            height = _int(pa.get("height"))
            left = _int(ma.get("left"))
            right = _int(ma.get("right"))
            top = _int(ma.get("top"))
            bottom = _int(ma.get("bottom"))
            gutter = _int(ma.get("gutter"))
            header = _int(ma.get("header"))
            footer = _int(ma.get("footer"))
            body_width = max(0, width - left - right - gutter) if width else 0
            body_height = max(0, height - top - bottom - header - footer) if height else 0
            sections.append({
                "section_index": section_index,
                "section": section_name,
                "page_width": width,
                "page_height": height,
                "landscape": pa.get("landscape"),
                "gutter_type": pa.get("gutterType"),
                "margins": {
                    "left": left,
                    "right": right,
                    "top": top,
                    "bottom": bottom,
                    "header": header,
                    "footer": footer,
                    "gutter": gutter,
                },
                "text_frame_width": body_width,
                "text_frame_height": body_height,
            })

    canonical_fonts = sorted(
        font_faces,
        key=lambda item: (
            str(item.get("name") or ""),
            str(item.get("lang") or ""),
            str(item.get("type") or ""),
        ),
    )
    font_inventory_hash = _sha256_json(canonical_fonts)
    geometry_hash = _sha256_json(sections)
    break_hash = _sha256_json({
        "paragraph_count": paragraph_count,
        "hard_line_breaks": hard_line_breaks,
        "explicit_page_breaks": explicit_page_breaks,
        "explicit_column_breaks": explicit_column_breaks,
    })
    return {
        "sections": sections,
        "section_count": len(sections),
        "paragraph_count": paragraph_count,
        "hard_break_receipt": {
            "hard_line_breaks": hard_line_breaks,
            "explicit_page_breaks": explicit_page_breaks,
            "explicit_column_breaks": explicit_column_breaks,
            "sha256": break_hash,
        },
        "font_inventory": canonical_fonts,
        "font_inventory_sha256": font_inventory_hash,
        "page_section_geometry_sha256": geometry_hash,
        "soft_wrap_authority": "EXTERNAL_RENDER_REQUIRED",
        "pagination_authority": "EXTERNAL_RENDER_REQUIRED",
        "authority": "PAGE_SECTION_GEOMETRY_AND_EXPLICIT_BREAK_RECEIPT",
    }


def _renderer_is_hancom(value: str) -> bool:
    text = str(value or "").casefold()
    return any(token in text for token in ("hancom", "hangul", "한컴", "한글"))


def adjudicate_layout_fidelity(
    structural_receipt: dict,
    render_receipt: dict,
) -> dict:
    """Fail-closed P3.10/P3.11 render authority adjudication.

    The caller supplies measured external-render evidence. This function never
    invents pagination, line-break, glyph, baseline or raster observations.
    """
    renderer = render_receipt.get("renderer") or {}
    environment = render_receipt.get("environment") or {}
    metrics = render_receipt.get("metrics") or {}
    calibration = render_receipt.get("calibration") or {}

    renderer_name = str(renderer.get("name") or "")
    renderer_version = str(renderer.get("version") or "")
    native_hancom = bool(renderer.get("hancom_native")) and _renderer_is_hancom(renderer_name)
    font_controlled = bool(environment.get("font_environment_controlled"))
    source_font_hash = str(environment.get("source_font_inventory_sha256") or "")
    target_font_hash = str(environment.get("target_font_inventory_sha256") or "")
    font_hash_match = bool(source_font_hash and source_font_hash == target_font_hash)

    pagination_equal = metrics.get("pagination_equal")
    line_break_equal = metrics.get("line_break_equal")
    exact_pixel_match = metrics.get("exact_pixel_match")
    pixel_diff_ratio = metrics.get("pixel_diff_ratio")
    mae = metrics.get("mae")
    edge_disagreement = metrics.get("edge_disagreement")
    bbox_delta = metrics.get("bbox_max_displacement_px")
    glyph_delta = metrics.get("glyph_advance_max_delta_px")
    baseline_delta = metrics.get("inline_baseline_max_delta_px")
    paint_diff = metrics.get("border_paint_diff_ratio")

    required_metric_names = (
        "pagination_equal",
        "line_break_equal",
        "exact_pixel_match",
        "pixel_diff_ratio",
        "mae",
        "edge_disagreement",
        "bbox_max_displacement_px",
        "glyph_advance_max_delta_px",
        "inline_baseline_max_delta_px",
        "border_paint_diff_ratio",
    )
    missing_metrics = [
        key for key in required_metric_names
        if key not in metrics or metrics.get(key) is None
    ]

    reason_chain: list[str] = []
    if not native_hancom:
        reason_chain.append("HANCOM_NATIVE_RENDER_WORLD_CONTACT_HOLD")
    if not font_controlled or not font_hash_match:
        reason_chain.append("FONT_ENVIRONMENT_UNCONTROLLED")
    if missing_metrics:
        reason_chain.append("RENDER_METRICS_INCOMPLETE")

    if pagination_equal is False:
        reason_chain.append("PAGINATION_LAYOUT_DIVERGENCE")
    elif line_break_equal is False:
        reason_chain.append("LINE_BREAK_DIVERGENCE")

    glyph_tol = float(calibration.get("glyph_advance_tolerance_px", 0.0))
    baseline_tol = float(calibration.get("inline_baseline_tolerance_px", 0.0))
    bbox_tol = float(calibration.get("bbox_displacement_tolerance_px", 0.0))
    paint_tol = float(calibration.get("border_paint_tolerance_ratio", 0.0))
    pixel_tol = float(calibration.get("pixel_diff_tolerance_ratio", 0.0))
    mae_tol = float(calibration.get("mae_tolerance", 0.0))
    edge_tol = float(calibration.get("edge_disagreement_tolerance", 0.0))

    if glyph_delta is not None and float(glyph_delta) > glyph_tol:
        reason_chain.append("FONT_METRIC_GLYPH_ADVANCE_DIVERGENCE")
    if baseline_delta is not None and float(baseline_delta) > baseline_tol:
        reason_chain.append("INLINE_OBJECT_BASELINE_DIVERGENCE")
    if bbox_delta is not None and float(bbox_delta) > bbox_tol:
        reason_chain.append("RENDERED_GEOMETRY_DISPLACEMENT")
    if paint_diff is not None and float(paint_diff) > paint_tol:
        reason_chain.append("BORDER_PAINT_RASTER_RESIDUE")

    calibrated_render_pass = (
        not missing_metrics
        and pagination_equal is True
        and line_break_equal is True
        and float(pixel_diff_ratio) <= pixel_tol
        and float(mae) <= mae_tol
        and float(edge_disagreement) <= edge_tol
        and float(bbox_delta) <= bbox_tol
        and float(glyph_delta) <= glyph_tol
        and float(baseline_delta) <= baseline_tol
        and float(paint_diff) <= paint_tol
    )

    full_pixel_pass = (
        native_hancom
        and font_controlled
        and font_hash_match
        and calibrated_render_pass
        and exact_pixel_match is True
    )

    if full_pixel_pass:
        verdict = "PIXEL_RENDER_FIDELITY_PASS"
        authority = "HANCOM_NATIVE_EXACT_PIXEL_AUTHORITY"
    elif calibrated_render_pass and native_hancom and font_controlled and font_hash_match:
        verdict = "RENDERER_NORMALIZED_FIDELITY_PASS / PIXEL_RENDER_FIDELITY_HOLD"
        authority = "HANCOM_NATIVE_CALIBRATED_RENDER_AUTHORITY"
    else:
        verdict = "PIXEL_RENDER_FIDELITY_HOLD"
        authority = "ATTRIBUTED_RENDER_RESIDUAL_ONLY"

    if exact_pixel_match is False and not any(
        item.endswith("DIVERGENCE") or item.endswith("RESIDUE")
        for item in reason_chain
    ):
        reason_chain.append("RASTERIZER_ONLY_RESIDUE_CANDIDATE")

    return {
        "verdict": verdict,
        "authority": authority,
        "renderer": {
            "name": renderer_name,
            "version": renderer_version,
            "hancom_native": native_hancom,
        },
        "environment": {
            "font_environment_controlled": font_controlled,
            "font_inventory_match": font_hash_match,
            "source_font_inventory_sha256": source_font_hash,
            "target_font_inventory_sha256": target_font_hash,
        },
        "structural": {
            "page_section_geometry_sha256": structural_receipt.get(
                "page_section_geometry_sha256"
            ),
            "hard_break_sha256": (
                structural_receipt.get("hard_break_receipt") or {}
            ).get("sha256"),
            "font_inventory_sha256": structural_receipt.get("font_inventory_sha256"),
        },
        "metrics": metrics,
        "calibration": {
            "pixel_diff_tolerance_ratio": pixel_tol,
            "mae_tolerance": mae_tol,
            "edge_disagreement_tolerance": edge_tol,
            "bbox_displacement_tolerance_px": bbox_tol,
            "glyph_advance_tolerance_px": glyph_tol,
            "inline_baseline_tolerance_px": baseline_tol,
            "border_paint_tolerance_ratio": paint_tol,
        },
        "missing_metrics": missing_metrics,
        "reason_chain": reason_chain,
        "promotion_gate": {
            "page_section_structural_receipt": bool(
                structural_receipt.get("page_section_geometry_sha256")
            ),
            "hancom_native_renderer": native_hancom,
            "font_environment_controlled": font_controlled and font_hash_match,
            "pagination_exact": pagination_equal is True,
            "line_break_exact": line_break_equal is True,
            "glyph_advance_within_calibration": (
                glyph_delta is not None and float(glyph_delta) <= glyph_tol
            ),
            "inline_baseline_within_calibration": (
                baseline_delta is not None and float(baseline_delta) <= baseline_tol
            ),
            "border_paint_within_calibration": (
                paint_diff is not None and float(paint_diff) <= paint_tol
            ),
            "calibrated_render_pass": calibrated_render_pass,
            "exact_pixel_match": exact_pixel_match is True,
        },
    }
