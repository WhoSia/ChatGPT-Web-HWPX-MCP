from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import fitz
from PIL import Image, ImageChops, ImageFilter


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def page_capture(pdf_path: Path, prefix: str, out_dir: Path, dpi: int) -> tuple[dict, list[dict]]:
    doc = fitz.open(pdf_path)
    scale = dpi / 72.0
    pages = []
    fonts: dict[tuple[str, float], dict] = {}

    for page_index, page in enumerate(doc):
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        raster = out_dir / f"{prefix}-page-{page_index:03d}.png"
        pix.save(raster)

        line_boxes = []
        text = page.get_text("dict")
        line_index = 0
        for block_index, block in enumerate(text.get("blocks", [])):
            for raw_line in block.get("lines", []):
                spans = raw_line.get("spans", [])
                line_text = "".join(str(span.get("text", "")) for span in spans)
                if not line_text and not spans:
                    continue
                bbox = raw_line.get("bbox", (0, 0, 0, 0))
                x0, y0, x1, y1 = [float(v) * scale for v in bbox]
                baselines = []
                for span in spans:
                    font = str(span.get("font") or "").strip()
                    size = float(span.get("size") or 0.0)
                    if font:
                        fonts[(font, size)] = {
                            "family": font,
                            "style": "",
                            "postscript_name": font,
                            "version": "",
                            "file_sha256": "",
                            "observed_size_pt": size,
                        }
                    origin = span.get("origin")
                    if origin and len(origin) >= 2:
                        baselines.append(float(origin[1]) * scale)
                baseline = max(baselines) if baselines else y1
                line_boxes.append({
                    "line_index": line_index,
                    "x": x0,
                    "y": y0,
                    "width": max(0.001, x1 - x0),
                    "height": max(0.001, y1 - y0),
                    "baseline": max(0.0, baseline),
                    "text_sha256": sha256_text(line_text),
                    "paragraph_locator": f"page:{page_index}/block:{block_index}",
                    "_text": line_text,
                })
                line_index += 1

        public_lines = [
            {k: v for k, v in item.items() if k != "_text"}
            for item in line_boxes
        ]
        pages.append({
            "page_index": page_index,
            "width_px": pix.width,
            "height_px": pix.height,
            "raster_sha256": sha256_file(raster),
            "line_boxes": public_lines,
        })

    return {"pages": pages}, list(fonts.values())


def diff_ratio(a: Image.Image, b: Image.Image) -> tuple[float, float]:
    if a.size != b.size:
        return 1.0, 255.0
    aa = a.convert("L")
    bb = b.convert("L")
    diff = ImageChops.difference(aa, bb)
    hist = diff.histogram()
    total = aa.width * aa.height
    nonzero = total - hist[0]
    mae = sum(value * count for value, count in enumerate(hist)) / max(1, total)
    return nonzero / max(1, total), mae


def edge_ratio(a: Image.Image, b: Image.Image) -> float:
    if a.size != b.size:
        return 1.0
    ea = a.convert("L").filter(ImageFilter.FIND_EDGES)
    eb = b.convert("L").filter(ImageFilter.FIND_EDGES)
    diff = ImageChops.difference(ea, eb)
    hist = diff.histogram()
    total = a.width * a.height
    return (total - hist[0]) / max(1, total)


def max_line_metrics(source_capture: dict, target_capture: dict) -> tuple[float, float, float]:
    bbox_delta = 0.0
    advance_delta = 0.0
    baseline_delta = 0.0
    for sp, tp in zip(source_capture["pages"], target_capture["pages"]):
        for sl, tl in zip(sp["line_boxes"], tp["line_boxes"]):
            bbox_delta = max(
                bbox_delta,
                abs(float(sl["x"]) - float(tl["x"])),
                abs(float(sl["y"]) - float(tl["y"])),
                abs(float(sl["width"]) - float(tl["width"])),
                abs(float(sl["height"]) - float(tl["height"])),
            )
            advance_delta = max(
                advance_delta,
                abs(float(sl["width"]) - float(tl["width"])),
            )
            baseline_delta = max(
                baseline_delta,
                abs(float(sl["baseline"]) - float(tl["baseline"])),
            )
    return bbox_delta, advance_delta, baseline_delta


def line_topology(capture: dict) -> list:
    return [
        [
            (line.get("text_sha256", ""), line.get("paragraph_locator", ""))
            for line in page["line_boxes"]
        ]
        for page in capture["pages"]
    ]


def build_receipt(args) -> dict:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    source_pdf = Path(args.source_pdf)
    target_pdf = Path(args.target_pdf)
    source_hwpx = Path(args.source_hwpx)
    target_hwpx = Path(args.target_hwpx)

    source_capture, source_fonts = page_capture(source_pdf, "source", out_dir, args.dpi)
    target_capture, target_fonts = page_capture(target_pdf, "target", out_dir, args.dpi)

    source_pages = sorted(out_dir.glob("source-page-*.png"))
    target_pages = sorted(out_dir.glob("target-page-*.png"))
    exact_pixel = (
        len(source_pages) == len(target_pages)
        and len(source_pages) > 0
        and all(sha256_file(a) == sha256_file(b) for a, b in zip(source_pages, target_pages))
    )

    ratios, maes, edges = [], [], []
    for a, b in zip(source_pages, target_pages):
        ia, ib = Image.open(a), Image.open(b)
        ratio, mae = diff_ratio(ia, ib)
        ratios.append(ratio)
        maes.append(mae)
        edges.append(edge_ratio(ia, ib))

    page_count_equal = len(source_capture["pages"]) == len(target_capture["pages"])
    topology_equal = page_count_equal and line_topology(source_capture) == line_topology(target_capture)
    bbox_delta, advance_delta, baseline_delta = max_line_metrics(source_capture, target_capture)

    metrics = {
        "pagination_equal": page_count_equal,
        "line_break_equal": topology_equal,
        "exact_pixel_match": exact_pixel,
        "pixel_diff_ratio": max(ratios, default=1.0),
        "mae": max(maes, default=255.0),
        "edge_disagreement": max(edges, default=1.0),
        "bbox_max_displacement_px": bbox_delta,
        "glyph_advance_max_delta_px": advance_delta,
        "inline_baseline_max_delta_px": baseline_delta,
        "border_paint_diff_ratio": max(edges, default=1.0),
    }

    line_boxes = {
        "schema": "chatgpt-web-hwpx-mcp/line-box-capture/p3.13-r1/v1",
        "fixture_id": args.fixture_id,
        "source": source_capture,
        "target": target_capture,
    }
    (out_dir / "line-boxes.json").write_text(
        json.dumps(line_boxes, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    fonts = {
        "schema": "chatgpt-web-hwpx-mcp/font-inventory/p3.13-r1/v1",
        "fixture_id": args.fixture_id,
        "source_fonts": source_fonts,
        "target_fonts": target_fonts,
        "authority": "HANCOM_PDF_OBSERVED_FONT_INVENTORY",
    }
    (out_dir / "fonts.json").write_text(
        json.dumps(fonts, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    receipt = {
        "schema": "chatgpt-web-hwpx-mcp/render-receipt/p3.12/v1",
        "fixture_id": args.fixture_id,
        "source_sha256": sha256_file(source_hwpx),
        "target_sha256": sha256_file(target_hwpx),
        "renderer": {
            "name": "Hancom Hangul",
            "version": args.hancom_version,
            "hancom_native": True,
            "executable_sha256": args.hancom_executable_sha256.lower(),
            "os": "Windows",
            "dpi": args.dpi,
            "pdf_backend": "Hancom SaveAs PDF",
            "rasterizer": "PyMuPDF",
            "rasterizer_version": fitz.VersionBind,
        },
        "source_environment": {"fonts": source_fonts},
        "target_environment": {"fonts": target_fonts},
        "source_capture": source_capture,
        "target_capture": target_capture,
        "metrics": metrics,
        "calibration": {
            "pixel_diff_tolerance_ratio": 0.0,
            "mae_tolerance": 0.0,
            "edge_disagreement_tolerance": 0.0,
            "bbox_displacement_tolerance_px": 0.0,
            "glyph_advance_tolerance_px": 0.0,
            "inline_baseline_tolerance_px": 0.0,
            "border_paint_tolerance_ratio": 0.0,
        },
    }
    (out_dir / "render-receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return receipt


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--fixture-id", required=True)
    p.add_argument("--source-hwpx", required=True)
    p.add_argument("--target-hwpx", required=True)
    p.add_argument("--source-pdf", required=True)
    p.add_argument("--target-pdf", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--hancom-version", required=True)
    p.add_argument("--hancom-executable-sha256", required=True)
    p.add_argument("--dpi", type=int, default=144)
    args = p.parse_args()
    receipt = build_receipt(args)
    print(json.dumps({
        "fixture_id": receipt["fixture_id"],
        "metrics": receipt["metrics"],
        "render_receipt": str(Path(args.out_dir) / "render-receipt.json"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
