from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "authorbench/p340r1-hancom-capture-pack/v1"
FIXTURES = (
    ("AUTHORBENCH_A2_FRESH", "authorbench-a2-research-data-infrastructure.hwpx", "FRESH_FIRST_COMPLETED_ARTIFACT"),
    ("AUTHORBENCH_A2_REPAIR_PROBE_BEFORE", "authorbench-a2-repair-probe-before.hwpx", "CONTROLLED_REPAIR_REGRESSION_BEFORE"),
    ("AUTHORBENCH_A2_REPAIR_PROBE_AFTER", "authorbench-a2-repair-probe-after.hwpx", "CONTROLLED_REPAIR_REGRESSION_AFTER"),
)
GENERATOR_INPUTS = (
    "benchmarks/authorbench_a1.py",
    "benchmarks/authorbench_a2.py",
    "benchmarks/authorbench_a2_p340_evaluation.py",
    "p340_feedback_loop.py",
    "p339_design_intelligence.py",
    "p338_rich_builder.py",
    "p321_document_composer.py",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def git_output(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def assert_clean_source(repo: Path) -> str:
    commit = git_output(repo, "rev-parse", "HEAD")
    tracked = git_output(repo, "status", "--porcelain", "--untracked-files=no")
    if tracked:
        raise RuntimeError("tracked working tree changes prevent exact source custody")
    return commit


def materialize(repo: Path, pack: Path) -> dict[str, Any]:
    repo = repo.resolve()
    pack = pack.resolve()
    if pack.exists():
        raise FileExistsError(f"refusing to overwrite existing run directory: {pack}")
    commit = assert_clean_source(repo)
    pack.mkdir(parents=True)

    for script in (
        "benchmarks/authorbench_a1.py",
        "benchmarks/authorbench_a2.py",
        "benchmarks/authorbench_a2_p340_evaluation.py",
    ):
        subprocess.run([sys.executable, script], cwd=repo, check=True)

    fixture_entries = []
    for fixture_id, filename, role in FIXTURES:
        source = repo / "artifacts" / filename
        if not source.is_file():
            raise RuntimeError(f"required materialized fixture missing: {source}")
        fixture_dir = pack / "fixtures" / fixture_id
        fixture_dir.mkdir(parents=True)
        target = fixture_dir / "input.hwpx"
        shutil.copy2(source, target)
        fixture_entries.append({
            "fixture_id": fixture_id,
            "role": role,
            "path": target.relative_to(pack).as_posix(),
            "sha256": sha256_file(target),
            "size": target.stat().st_size,
        })

    manifest = {
        "schema": SCHEMA,
        "phase": "P3.40-R1",
        "source": {
            "repository": "https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP.git",
            "commit": commit,
            "tracked_tree_clean": True,
            "generator_inputs": [
                {"path": p, "sha256": sha256_file(repo / p)} for p in GENERATOR_INPUTS
            ],
        },
        "materialized_at_utc": utc_now(),
        "fixtures": fixture_entries,
        "capture_contract": {
            "renderer": "Hancom Hangul",
            "pdf_backend": "Hancom SaveAs PDF",
            "rasterizer": "PyMuPDF",
            "required": ["renderer_version", "hwp_executable_sha256", "dpi", "page_raster_sha256", "font_inventory", "custody"],
            "authority": "NATIVE_RENDER_OBSERVATION_NOT_HUMAN_DESIGN_VERDICT",
        },
    }
    write_json(pack / "capture-ready-manifest.json", manifest)
    return manifest


def verify_fixture(pack: Path, fixture: dict[str, Any]) -> Path:
    path = pack / str(fixture["path"])
    if not path.is_file():
        raise RuntimeError(f"fixture missing: {path}")
    actual = sha256_file(path)
    if actual != fixture["sha256"]:
        raise RuntimeError(f"fixture hash mismatch for {fixture['fixture_id']}: expected {fixture['sha256']}, got {actual}")
    return path


def capture_pdf(
    *, pack: Path, fixture_id: str, pdf: Path, hancom_version: str,
    hancom_sha256: str, dpi: int, runner_sha256: str,
) -> dict[str, Any]:
    # Keep materialization/hash validation usable before capture dependencies are
    # installed; EnvBootstrap supplies PyMuPDF/Pillow for this world-contact step.
    from scripts.p313r1_pdf_capture import page_capture

    manifest = read_json(pack / "capture-ready-manifest.json")
    fixture = next((x for x in manifest["fixtures"] if x["fixture_id"] == fixture_id), None)
    if fixture is None:
        raise RuntimeError(f"unknown fixture id: {fixture_id}")
    input_path = verify_fixture(pack, fixture)
    if not pdf.is_file() or pdf.stat().st_size <= 0:
        raise RuntimeError(f"missing or empty Hancom PDF: {pdf}")
    capture_dir = pack / "fixtures" / fixture_id / "capture"
    capture_dir.mkdir(parents=True, exist_ok=True)
    capture, fonts = page_capture(pdf, "page", capture_dir, dpi)
    if not capture["pages"]:
        raise RuntimeError(f"Hancom PDF has no pages: {pdf}")
    font_payload = {
        "schema": "chatgpt-web-hwpx-mcp/font-inventory/p3.13-r1/v1",
        "fixture_id": fixture_id,
        "fonts": fonts,
        "authority": "HANCOM_PDF_OBSERVED_FONT_INVENTORY",
    }
    write_json(capture_dir / "fonts.json", font_payload)
    receipt = {
        "schema": "chatgpt-web-hwpx-mcp/render-receipt/p3.12/v1",
        "phase": "P3.40-R1",
        "fixture_id": fixture_id,
        "source_commit": manifest["source"]["commit"],
        "source_sha256": fixture["sha256"],
        "source_size": fixture["size"],
        "pdf_sha256": sha256_file(pdf),
        "renderer": {
            "name": "Hancom Hangul", "version": hancom_version, "hancom_native": True,
            "executable_sha256": hancom_sha256.lower(), "os": "Windows", "dpi": dpi,
            "pdf_backend": "Hancom SaveAs PDF", "rasterizer": "PyMuPDF",
        },
        "capture": capture,
        "font_inventory": "fonts.json",
        "custody": {
            "capture_ready_manifest_sha256": sha256_file(pack / "capture-ready-manifest.json"),
            "runner_sha256": runner_sha256.lower(),
            "captured_at_utc": utc_now(),
            "authority": "NATIVE_HANCOM_RENDER_OBSERVATION",
        },
    }
    write_json(capture_dir / "render-receipt.json", receipt)
    return receipt


def validate_complete(pack: Path) -> dict[str, Any]:
    manifest = read_json(pack / "capture-ready-manifest.json")
    failures = []
    receipts = []
    for fixture in manifest["fixtures"]:
        try:
            verify_fixture(pack, fixture)
            receipt_path = pack / "fixtures" / fixture["fixture_id"] / "capture" / "render-receipt.json"
            receipt = read_json(receipt_path)
            if receipt.get("source_sha256") != fixture["sha256"]:
                raise RuntimeError("receipt source hash does not match frozen fixture")
            if not receipt.get("capture", {}).get("pages"):
                raise RuntimeError("receipt contains no page raster evidence")
            receipts.append({"fixture_id": fixture["fixture_id"], "receipt_sha256": sha256_file(receipt_path)})
        except Exception as exc:  # preserve per-fixture isolation in the final receipt
            failures.append({"fixture_id": fixture["fixture_id"], "error": str(exc)})
    return {"complete": not failures, "receipts": receipts, "failures": failures}


def deterministic_zip(pack: Path, destination: Path) -> str:
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite captured ZIP: {destination}")
    files = sorted(p for p in pack.rglob("*") if p.is_file())
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            info = zipfile.ZipInfo(path.relative_to(pack).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    return sha256_file(destination)
