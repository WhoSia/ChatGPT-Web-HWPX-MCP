"""P4.24 native-PDF visual regression signals for local acceptance.

Read two PDFs at the same resolution. Report page-level changed-pixel
fractions WITHOUT claiming that low pixel difference proves correctness.
The caller must inspect every page (and semantic/math content) separately.

Optional local developer dependency: pip install pymupdf
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare_pdf_pages(
    baseline: Path,
    candidate: Path,
    *,
    dpi: int = 96,
    pixel_delta_threshold: int = 10,
    maximum_pages: int = 150,
) -> dict[str, Any]:
    """Compare grayscale rasterizations; never export original page text."""
    if type(dpi) is not int or not 72 <= dpi <= 200:
        raise ValueError("dpi must be in 72..200")
    if type(pixel_delta_threshold) is not int or not 0 <= pixel_delta_threshold <= 255:
        raise ValueError("pixel delta threshold must be in 0..255")
    if type(maximum_pages) is not int or not 1 <= maximum_pages <= 200:
        raise ValueError("maximum_pages must be in 1..200")
    import fitz  # optional developer-only dependency
    baseline = Path(baseline).resolve(strict=True)
    candidate = Path(candidate).resolve(strict=True)
    if baseline.suffix.lower() != ".pdf" or candidate.suffix.lower() != ".pdf":
        raise ValueError("both references must be PDFs")
    pages = []
    scale = dpi / 72
    with fitz.open(baseline) as before, fitz.open(candidate) as after:
        if before.page_count > maximum_pages or after.page_count > maximum_pages:
            raise ValueError("PDF exceeds maximum page count for local visual audit")
        for i in range(max(before.page_count, after.page_count)):
            if i >= before.page_count or i >= after.page_count:
                pages.append({
                    "page": i + 1,
                    "same_dimensions": False,
                    "status": "MISSING_PAGE",
                })
                continue
            first = before[i].get_pixmap(
                matrix=fitz.Matrix(scale, scale), colorspace=fitz.csGRAY, alpha=False
            )
            second = after[i].get_pixmap(
                matrix=fitz.Matrix(scale, scale), colorspace=fitz.csGRAY, alpha=False
            )
            if first.width != second.width or first.height != second.height:
                pages.append({
                    "page": i + 1,
                    "same_dimensions": False,
                    "status": "PAGE_GEOMETRY_CHANGED",
                })
                continue
            # Grayscale byte arrays: no numpy dependency in the production MCP.
            total = first.width * first.height
            count = 0
            total_delta = 0
            for x, y in zip(first.samples, second.samples):
                delta = abs(x - y)
                count += delta > pixel_delta_threshold
                total_delta += delta
            pages.append({
                "page": i + 1,
                "same_dimensions": True,
                "status": "RASTER_COMPARED",
                "fraction_changed_pixels": round(count / total, 6),
                "mean_grayscale_delta": round(total_delta / total, 5),
            })
        return {
            "schema": "p424.native-pdf.visual-diff.v1",
            "baseline_sha256": _sha256(baseline),
            "candidate_sha256": _sha256(candidate),
            "baseline_pages": before.page_count,
            "candidate_pages": after.page_count,
            "dpi": dpi,
            "pixel_delta_threshold": pixel_delta_threshold,
            "pages": pages,
            "native_hancom_render_verified": False,
            "visual_acceptance": "REQUIRES_HUMAN_PAGE_REVIEW",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect page-wise PDF raster differences")
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--dpi", type=int, default=96)
    args = parser.parse_args()
    print(json.dumps(compare_pdf_pages(args.baseline, args.candidate, dpi=args.dpi),
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
