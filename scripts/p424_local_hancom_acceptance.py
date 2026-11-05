"""P4.24 local Work acceptance: source HWPX -> real Hancom PDF -> page diff.

This is a single, non-destructive local user-job entrypoint.
Every accepted report remains explicitly unreviewed until a human inspects
the rendered pages. Windows Hangul must actually run through the WSL bridge.

Usage:
  python scripts/p424_local_hancom_acceptance.py \
      source.hwpx --output-dir /mnt/c/acceptance \
      --baseline-pdf /mnt/c/accepted/source.pdf

Developer-only optional dependency for visual diff: pymupdf.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from p423_wsl_hancom_pdf_bridge import export_wsl_native_pdf
from p424_pdf_visual_compare import compare_pdf_pages


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1 << 20), b""):
            digest.update(part)
    return digest.hexdigest()


def run_local_acceptance(
    source: Path,
    output_directory: Path,
    *,
    baseline_pdf: Path | None = None,
    dpi: int = 96,
) -> dict:
    """Return a truthful receipt; do not open or overwrite any unrelated file."""
    source = Path(source).resolve(strict=True)
    output_directory = Path(output_directory).resolve(strict=True)
    if source.suffix.lower() != ".hwpx":
        raise ValueError("source must be a native .hwpx file")
    if not output_directory.is_dir():
        raise ValueError("output directory must already exist")
    native_pdf = output_directory / (source.stem + ".native-hancom.pdf")
    manifest = output_directory / (source.stem + ".p424-acceptance.json")
    if native_pdf.exists() or manifest.exists():
        raise FileExistsError("an acceptance artifact already exists; use a fresh output directory")
    baseline = Path(baseline_pdf).resolve(strict=True) if baseline_pdf else None
    if baseline is not None and baseline.suffix.lower() != ".pdf":
        raise ValueError("baseline must be an existing PDF")
    before = _sha(source)
    native_receipt = export_wsl_native_pdf(source, native_pdf)
    if not native_pdf.is_file() or native_pdf.read_bytes()[:5] != b"%PDF-":
        raise RuntimeError("native conversion has not produced a recognized PDF")
    if _sha(source) != before:
        raise RuntimeError("source HWPX changed during native conversion")
    pdf_sha = _sha(native_pdf)
    if native_receipt.get("pdf_sha256") != pdf_sha:
        raise RuntimeError("native PDF digest differs from converter receipt")
    visual_diff = (
        compare_pdf_pages(baseline, native_pdf, dpi=dpi)
        if baseline is not None else None
    )
    result = {
        "schema": "p424.local-work.native-hancom-acceptance.v1",
        "source_hwpx_sha256": before,
        "source_hwpx_file": source.name,
        "native_pdf_file": native_pdf.name,
        "native_pdf_sha256": pdf_sha,
        "native_pdf_bytes": native_pdf.stat().st_size,
        "native_engine": "HANCOM_HWP_EXE_COM",
        "hancom_product_version": native_receipt.get("hancom_product_version"),
        "hancom_executable_sha256": native_receipt.get("hancom_executable_sha256"),
        "pdf_page_diff": visual_diff,
        "native_pdf_created": True,
        "visual_acceptance": "REQUIRES_HUMAN_PAGE_REVIEW",
        "production_approved": False,
    }
    # No private document text or equation scripts in the manifest.
    manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Native Hancom PDF + visual comparison")
    parser.add_argument("source", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--baseline-pdf", type=Path)
    parser.add_argument("--dpi", type=int, default=96)
    args = parser.parse_args()
    try:
        report = run_local_acceptance(
            args.source, args.output_dir, baseline_pdf=args.baseline_pdf,
            dpi=args.dpi,
        )
    except (RuntimeError, OSError, ValueError, ImportError) as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
