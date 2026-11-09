"""Batch native Hancom PDF conversion for the already-proven local WSL bridge.

Usage:
  python scripts/p424_batch_native_pdf.py /mnt/c/Users/me/Documents/hwpx \
    --output-dir /mnt/c/p424-validation/batch --recursive

Uses existing p424_local_hancom_acceptance per file, not a second renderer.
Each input receives its own deterministic output directory. Re-running
reuses only artifacts whose source SHA, PDF SHA and byte count match.
Never reclassifies unreviewed output as visually approved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Callable

from p424_local_hancom_acceptance import run_local_acceptance


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _directory_name(source: Path) -> str:
    # Hash the absolute path so identical names in different folders are
    # still independent jobs. No source content is put into output filenames.
    stem = re.sub(r"[^A-Za-z0-9가-힣_-]+", "-", source.stem).strip("-")[:64] or "document"
    identity = hashlib.sha256(str(source.resolve()).encode("utf-8")).hexdigest()[:16]
    return f"{stem}-{identity}"


def _reuse_verified(source: Path, job_dir: Path) -> dict | None:
    manifest = job_dir / (source.stem + ".p424-acceptance.json")
    pdf = job_dir / (source.stem + ".native-hancom.pdf")
    if not manifest.is_file() or not pdf.is_file():
        return None
    try:
        record = json.loads(manifest.read_text(encoding="utf-8"))
        if (
            record.get("schema") != "p424.local-work.native-hancom-acceptance.v1"
            or record.get("native_pdf_created") is not True
            or record.get("source_hwpx_sha256") != _sha(source)
            or record.get("native_pdf_sha256") != _sha(pdf)
            or record.get("native_pdf_bytes") != pdf.stat().st_size
            or record.get("native_pdf_file") != pdf.name
        ):
            return None
        with pdf.open("rb") as reader:
            if reader.read(5) != b"%PDF-":
                return None
        return record
    except (OSError, ValueError, KeyError, TypeError):
        return None


def convert_batch(
    paths: list[Path],
    output_directory: Path,
    *,
    recursive: bool = False,
    conversion: Callable = run_local_acceptance,
    dry_run: bool = False,
) -> dict:
    """Sequential conversion: minimize COM conflicts and preserve failures."""
    output_directory = Path(output_directory).resolve()
    if not output_directory.is_dir():
        raise FileNotFoundError("Create --output-dir before running")
    sources: dict[str, Path] = {}
    for user_path in paths:
        target = Path(user_path).resolve(strict=True)
        candidates = (
            [target] if target.is_file()
            else (target.rglob("*.hwpx") if recursive else target.glob("*.hwpx"))
        )
        for item in candidates:
            if item.is_file() and item.suffix.lower() == ".hwpx":
                source = item.resolve(strict=True)
                sources[str(source)] = source
    results: list[dict] = []
    for source in sorted(sources.values(), key=lambda x: str(x)):
        job_dir = output_directory / _directory_name(source)
        # Prevent accidentally discovering generated files recursively.
        if source.is_relative_to(output_directory):
            results.append({"source": str(source), "status": "SKIPPED_OUTPUT_TREE"})
            continue
        if dry_run and not job_dir.exists():
            results.append({
                "source": str(source), "status": "WOULD_CREATE",
                "output_directory": str(job_dir),
            })
            continue
        if not dry_run:
            job_dir.mkdir(exist_ok=True)
        reusable = _reuse_verified(source, job_dir)
        if reusable is not None:
            results.append({
                "source": str(source), "status": "REUSED_VERIFIED",
                "pdf_path": str(job_dir / reusable["native_pdf_file"]),
                "pdf_sha256": reusable["native_pdf_sha256"],
                "visual_acceptance": reusable["visual_acceptance"],
            })
            continue
        if job_dir.exists() and any(job_dir.iterdir()):
            results.append({
                "source": str(source), "status": "BLOCKED_EXISTING_ARTIFACTS",
                "error": "Existing artifacts differ from source or are incomplete; move to a fresh output root",
            })
            continue
        if dry_run:
            results.append({
                "source": str(source), "status": "WOULD_CREATE",
                "output_directory": str(job_dir),
            })
            continue
        try:
            record = conversion(source, job_dir)
            results.append({
                "source": str(source), "status": "CREATED_UNREVIEWED",
                "pdf_path": str(job_dir / record["native_pdf_file"]),
                "pdf_sha256": record["native_pdf_sha256"],
                "visual_acceptance": record["visual_acceptance"],
            })
        except Exception as error:
            # Batch continues with other independent documents; no
            # arbitrary file cleanup or overwrite after partial conversion.
            results.append({
                "source": str(source), "status": "FAILED",
                "error": f"{type(error).__name__}: {error}",
            })
    tally = {s: sum(x["status"] == s for x in results) for s in (
        "CREATED_UNREVIEWED", "REUSED_VERIFIED", "FAILED",
        "BLOCKED_EXISTING_ARTIFACTS", "SKIPPED_OUTPUT_TREE", "WOULD_CREATE",
    )}
    report = {
        "schema": "p424.local-native-batch.v1",
        "output_root": str(output_directory),
        "total_inputs": len(sources),
        "summary": tally,
        "results": results,
        "production_approved": False,
        "visual_review_required": True,
        "dry_run": bool(dry_run),
    }
    # A stable report filename is convenient for local use; the report is
    # aggregate metadata only, not a replacement for each job's evidence.
    report_path = output_directory / "p424-batch-report.json"
    if not dry_run:
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch HWPX → native Hancom PDF via existing WSL bridge")
    parser.add_argument("paths", nargs="+", type=Path, help="HWPX files or directories")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--dry-run", action="store_true",
                        help="List conversion and reuse decisions without writing or invoking Hancom")
    args = parser.parse_args()
    try:
        report = convert_batch(args.paths, args.output_dir, recursive=args.recursive,
                               dry_run=args.dry_run)
    except (OSError, ValueError) as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["summary"]["FAILED"] or report["summary"]["BLOCKED_EXISTING_ARTIFACTS"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
