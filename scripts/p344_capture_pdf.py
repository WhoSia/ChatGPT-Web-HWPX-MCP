from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from p341_page_composition import diagnose_page_composition
from scripts.p313r1_pdf_capture import page_capture

SCHEMA = "authorbench/p3.44/native-render-receipt/v1"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--pack", required=True)
    p.add_argument("--fixture-id", required=True)
    p.add_argument("--pdf", required=True)
    p.add_argument("--hancom-version", required=True)
    p.add_argument("--hancom-sha256", required=True)
    p.add_argument("--dpi", type=int, required=True)
    p.add_argument("--runner-sha256", required=True)
    args = p.parse_args()

    pack = Path(args.pack).resolve()
    manifest_path = pack / "capture-ready-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    fixture = next(
        (x for x in manifest.get("fixtures", []) if x.get("fixture_id") == args.fixture_id),
        None,
    )
    if fixture is None:
        raise RuntimeError(f"unknown P3.44 fixture: {args.fixture_id}")

    source = pack / str(fixture["path"])
    if not source.is_file():
        raise RuntimeError(f"missing P3.44 source fixture: {source}")
    source_sha = sha256_file(source)
    if source_sha != fixture["sha256"]:
        raise RuntimeError(
            f"source hash mismatch for {args.fixture_id}: {source_sha} != {fixture['sha256']}"
        )

    pdf = Path(args.pdf).resolve()
    if not pdf.is_file() or pdf.stat().st_size <= 0:
        raise RuntimeError(f"missing or empty Hancom PDF: {pdf}")

    capture_dir = pack / "fixtures" / args.fixture_id / "capture"
    capture_dir.mkdir(parents=True, exist_ok=True)
    capture, fonts = page_capture(pdf, "page", capture_dir, int(args.dpi))
    if not capture.get("pages"):
        raise RuntimeError("native PDF produced zero pages")

    renderer = {
        "name": "Hancom Hangul",
        "version": str(args.hancom_version),
        "hancom_native": True,
        "executable_sha256": str(args.hancom_sha256).lower(),
        "os": "Windows",
        "dpi": int(args.dpi),
        "pdf_backend": "Hancom SaveAs PDF",
        "rasterizer": "PyMuPDF",
    }
    diagnostic = diagnose_page_composition(
        capture,
        renderer=renderer,
        archetype=str(fixture.get("archetype") or "POLISHED_REPORT"),
    )
    if not diagnostic.get("world_contact_valid"):
        raise RuntimeError("P3.44 page-composition diagnostic rejected native world contact")

    severity_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}
    for finding in diagnostic.get("findings") or []:
        sev = str((finding or {}).get("severity") or "LOW").upper()
        if sev in severity_counts:
            severity_counts[sev] += 1

    write_json(
        capture_dir / "fonts.json",
        {
            "schema": "authorbench/p3.44/font-inventory/v1",
            "fixture_id": args.fixture_id,
            "fonts": fonts,
            "authority": "HANCOM_PDF_OBSERVED_FONT_INVENTORY",
        },
    )
    write_json(capture_dir / "page-composition-diagnostic.json", diagnostic)

    receipt = {
        "schema": SCHEMA,
        "phase": "P3.44",
        "fixture_id": args.fixture_id,
        "source_first_pass_commit": manifest["source_commit"],
        "frozen_manifest_sha256": manifest["frozen_manifest_sha256"],
        "source_sha256": source_sha,
        "pdf_sha256": sha256_file(pdf),
        "renderer": renderer,
        "page_count": len(capture["pages"]),
        "page_raster_sha256": [str(x.get("sha256") or "") for x in capture["pages"]],
        "diagnostic": {
            "verdict": diagnostic["verdict"],
            "world_contact_valid": bool(diagnostic["world_contact_valid"]),
            "authority": diagnostic["authority"],
            "severity_counts": severity_counts,
            "finding_codes": sorted(
                str(x.get("code"))
                for x in (diagnostic.get("findings") or [])
                if x.get("code")
            ),
            "diagnostic_sha256": sha256_file(capture_dir / "page-composition-diagnostic.json"),
        },
        "custody": {
            "capture_ready_manifest_sha256": sha256_file(manifest_path),
            "runner_sha256": str(args.runner_sha256).lower(),
            "captured_at_utc": datetime.now(timezone.utc).isoformat(),
            "authority": "P3.44_NATIVE_HANCOM_RENDER_OBSERVATION",
        },
        "authority": "HANCOM_NATIVE_RENDER_EVIDENCE_NOT_HUMAN_VISUAL_APPROVAL",
    }
    write_json(capture_dir / "render-receipt.json", receipt)
    print(json.dumps({
        "fixture_id": args.fixture_id,
        "page_count": receipt["page_count"],
        "verdict": receipt["diagnostic"]["verdict"],
        "world_contact_valid": receipt["diagnostic"]["world_contact_valid"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
