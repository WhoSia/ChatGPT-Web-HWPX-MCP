#!/usr/bin/env python3
"""Create a self-contained, synthetic P4.26 scientific-report HWPX artifact.

Run:
    python scripts/p426_generate_native_showcase.py --output-dir /tmp/p426-showcase

Uses only this repository's native composer, normalizers, and readers. No
private document, Windows COM, Postgres, or remote renderer is required.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import struct
import zlib
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from hwpx_mcp.document.p2_document import build_document_map
from hwpx_mcp.document.p210_equations import build_equation_map
from hwpx_mcp.document.p29_objects import build_object_map
from hwpx_mcp.document.p318_document_setup import build_document_setup_map
from hwpx_mcp.document.p319_structured_publishing import build_structured_publishing_map
from hwpx_mcp.document.p320_annotation_apparatus import build_annotation_apparatus_map
from hwpx_mcp.document.p323_advanced_tables import build_advanced_table_map
from hwpx_mcp.document.p321_document_composer import compose_document_plan
from hwpx_mcp.interfaces.p425_report_presets import build_report_plan
from hwpx_mcp.orchestration.p338_rich_builder import compile_rich_document_plan


def _chunk(kind: bytes, data: bytes) -> bytes:
    assert len(kind) == 4
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def make_synthetic_curve_png() -> bytes:
    """Pure-stdlib 640x360 PNG with original grid, axes, 12 measured points."""
    width, height = 640, 360
    pixels = bytearray(b"\xff" * (width * height * 3))

    def dot(x: int, y: int, color: tuple[int, int, int], radius: int = 0) -> None:
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                xx, yy = x + dx, y + dy
                if 0 <= xx < width and 0 <= yy < height:
                    at = (yy * width + xx) * 3
                    pixels[at:at + 3] = bytes(color)

    def line(x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]) -> None:
        steps = max(abs(x1 - x0), abs(y1 - y0), 1)
        for t in range(steps + 1):
            dot(round(x0 + (x1 - x0) * t / steps),
                round(y0 + (y1 - y0) * t / steps), color)

    # Axes and 0..12 V, 0..0.60 A reference grid.
    left, right, bottom, top = 66, 604, 311, 35
    for i in range(7):
        y = bottom - round(i * (bottom - top) / 6)
        line(left, y, right, y, (228, 232, 237))
    for i in range(7):
        x = left + round(i * (right - left) / 6)
        line(x, top, x, bottom, (228, 232, 237))
    line(left, top, left, bottom, (45, 56, 68))
    line(left, bottom, right, bottom, (45, 56, 68))

    values = [(v, v / 20) for v in range(0, 13)]
    coords = []
    for voltage, current in values:
        x = left + round(voltage * (right - left) / 12)
        y = bottom - round(current * (bottom - top) / 0.60)
        coords.append((x, y))
    for (x0, y0), (x1, y1) in zip(coords, coords[1:]):
        line(x0, y0, x1, y1, (24, 98, 151))
    for x, y in coords:
        dot(x, y, (181, 66, 57), radius=3)

    # PNG RGB 8-bit, no external plotting library or font dependency.
    scanlines = b"".join(
        b"\x00" + bytes(pixels[y * width * 3:(y + 1) * width * 3])
        for y in range(height)
    )
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(scanlines, 9))
        + _chunk(b"IEND", b"")
    )


def create_showcase(output_dir: Path) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = "P426_합성_전기회로_실험보고서.hwpx"
    destination = output_dir / filename
    if destination.exists():
        raise FileExistsError(f"Will not overwrite existing example: {destination}")

    plot = make_synthetic_curve_png()
    plot_b64 = base64.b64encode(plot).decode("ascii")
    records = [["전압 (V)", "전류 (A)", "저항 (Ω)"]] + [
        [f"{i / 2:.1f}", f"{i / 40:.3f}", "20.0"]
        for i in range(1, 80)
    ]
    request = build_report_plan(
        title="합성 전기 회로 실험 보고서",
        author="P4.26 재현성 테스트",
        preset="science-report",
        layout={"base": "science-lab",
                "typography": {"body_line_percent": 160}},
        table_of_contents=True,
        page_numbers=True,
        number_captions=True,
        fit_figures_to_page=True,
        sections=[
            {"heading": "연구 배경", "content": [
                {"type": "paragraph", "id": "scope", "bookmark": "StudyScope",
                 "text": "본 문서의 모든 값은 소프트웨어 기능 검증을 위한 합성 데이터이다.",
                 "footnote": "실측 자료가 아니며 실제 전기 안전성이나 측정 정확도의 증거로 사용할 수 없다."},
                {"type": "paragraph", "text": "저항값 20 Ω인 이상적인 선형 회로를 가정하였다."},
            ]},
            {"heading": "이론적 분석", "content": [
                {"type": "paragraph", "text": "회로의 전압과 전류 사이의 관계는 다음과 같다."},
                {"type": "equation", "latex": r"V=IR", "caption": "옴의 법칙"},
                {"type": "equation", "latex": r"\frac{V}{I}=R", "caption": "저항의 정의"},
                {"type": "paragraph", "id": "theory_ref",
                 "text": "위 관계는 앞서 제시한 연구 범위를 따른다. ",
                 "page_ref_target": "scope"},
            ]},
            {"heading": "합성 실험 결과", "content": [
                {"type": "paragraph", "text": "전압을 변화시키며 이론값으로 계산한 전류의 선형 변화를 표시하였다."},
                {"type": "figure", "image_format": "png",
                 "content_base64": plot_b64,
                 "width": 85000, "height": 48000,
                 "caption": "전압과 전류의 합성 선형 관계"},
                {"type": "paragraph", "text": "아래 표는 긴 표의 분할과 반복 머리글 기능 검증을 위해 80행으로 구성하였다."},
                {"type": "table", "cells": records, "first_row_header": True,
                 "caption": "전압과 전류의 합성 측정값",
                 "table_format": {"page_break": "CELL", "repeat_header": True,
                                  "border_color": "#345C79"}},
            ]},
            {"heading": "결론 및 한계", "content": [
                {"type": "paragraph", "text": "본 예제는 HWPX 내부 문단·표·그림·수식·각주·참조 객체를 검증한다."},
                {"type": "paragraph", "text": "실제 한컴 PDF의 페이지 수와 시각적 배치는 별도로 검증해야 한다."},
            ]},
        ],
    )
    compiled = compile_rich_document_plan(request)
    receipt = compose_document_plan(destination, compiled["plan"])

    # Independently reread exactly the HWPX that will be published.
    paragraphs = build_document_map(destination)
    tables = build_advanced_table_map(destination)["tables"]
    equations = build_equation_map(destination)["equations"]
    objects = build_object_map(destination)
    notes = build_annotation_apparatus_map(destination)
    publishing = build_structured_publishing_map(destination)
    setup = build_document_setup_map(destination)
    with zipfile.ZipFile(destination, "r") as archive:
        if archive.testzip() is not None:
            raise AssertionError("Showcase HWPX has corrupt ZIP entries")
        for entry in archive.namelist():
            if entry.lower().endswith(".xml"):
                ElementTree.fromstring(archive.read(entry))

    assert receipt["atomic_commit"], "Native composition is not atomic"
    assert len(tables) == 1 and tables[0]["rows"] == 80
    assert len(tables[0]["cells"]) == 240
    assert tables[0]["repeat_header"] and tables[0]["page_break"] == "CELL"
    assert len(equations) == 2 and len(objects["pictures"]) == 1
    assert notes["counts"]["footnotes"] == 1
    assert any(item["name"] == "StudyScope" for item in publishing["bookmarks"])
    assert publishing["crossref_field_count"] >= 1
    assert setup["section_count"] >= 1

    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    summary = {
        "schema": "chatgpt-web-hwpx-mcp/p426/showcase-acceptance/v1",
        "filename": filename,
        "native_hwpx_sha256": digest,
        "size_bytes": destination.stat().st_size,
        "compiled_plan_sha256": compiled["plan_sha256"],
        "native_tables": len(tables),
        "table_rows": tables[0]["rows"],
        "table_cells": len(tables[0]["cells"]),
        "table_break_policy": tables[0]["page_break"],
        "native_repeat_header": tables[0]["repeat_header"],
        "native_pictures": len(objects["pictures"]),
        "picture_geometry": [
            {"width": item["width"], "height": item["height"]}
            for item in objects["pictures"]
        ],
        "native_equations": len(equations),
        "native_footnotes": notes["counts"]["footnotes"],
        "native_bookmarks": len(publishing["bookmarks"]),
        "native_crossrefs": publishing["crossref_field_count"],
        "native_sections": setup["section_count"],
        "native_body_paragraphs": len(paragraphs["paragraphs"]),
        "source_data": "SYNTHETIC_NONEMPIRICAL",
        "page_count_verified": False,
        "windows_hancom_render_verified": False,
        "chatgpt_host_delivery_verified": False,
    }
    (output_dir / "P426_생성검증_manifest.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    options = parser.parse_args()
    print(json.dumps(create_showcase(options.output_dir), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
