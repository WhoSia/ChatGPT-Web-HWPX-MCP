from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from p340r1_capture_pack import (
    assert_clean_source,
    deterministic_zip,
    read_json,
    sha256_file,
    utc_now,
    write_json,
)
from p341_page_composition import diagnose_page_composition

SCHEMA = "authorbench/p341r1-hancom-capture-pack/v1"
PHASE = "P3.41-R1"
FROZEN_BENCHMARK_COMMIT = "7872a8a5cf063c547f65ccd823d1063a51c17ee1"

FIXTURES = (
    {
        "fixture_id": "AUTHORBENCH_A3_RESEARCH_BRIEF",
        "filename": "authorbench-a3-research-brief.hwpx",
        "archetype": "RESEARCH_BRIEF",
        "sha256": "de7ae36c3f6d1602f1b8f6f846349ac8737b5c2e33b918b2d96a4ad7b9974555",
    },
    {
        "fixture_id": "AUTHORBENCH_A3_INSTITUTIONAL_REPORT",
        "filename": "authorbench-a3-institutional-report.hwpx",
        "archetype": "INSTITUTIONAL_REPORT",
        "sha256": "bc14b5a8b13bf473c2ad0b484d3b8b7a16accb8b8b8359853fdb221dddd5bcff",
    },
    {
        "fixture_id": "AUTHORBENCH_A3_ACADEMIC_REPORT",
        "filename": "authorbench-a3-academic-report.hwpx",
        "archetype": "ACADEMIC_REPORT",
        "sha256": "32b42461d4645b8db417b06b9db0518539900afc39e39ea39f2f7c501e023163",
    },
)

GENERATOR_INPUTS = (
    "benchmarks/authorbench_a3.py",
    "benchmarks/authorbench_a3_p341_evaluation.py",
    "p321_document_composer.py",
    "p338_rich_builder.py",
    "p339_design_intelligence.py",
    "p340_feedback_loop.py",
    "p341_page_composition.py",
)


def materialize(repo: Path, pack: Path) -> dict[str, Any]:
    repo = repo.resolve()
    pack = pack.resolve()
    if pack.exists():
        raise FileExistsError(f"refusing to overwrite existing run directory: {pack}")
    source_commit = assert_clean_source(repo)
    pack.mkdir(parents=True)

    subprocess.run([sys.executable, "benchmarks/authorbench_a3.py"], cwd=repo, check=True)
    subprocess.run([sys.executable, "benchmarks/authorbench_a3_p341_evaluation.py"], cwd=repo, check=True)

    receipt_src = repo / "artifacts" / "authorbench-a3-receipt.json"
    evaluation_src = repo / "artifacts" / "authorbench-a3-p341-evaluation.json"
    receipt = read_json(receipt_src)
    evaluation = read_json(evaluation_src)
    verdict = (
        evaluation.get("fresh_cross_archetype_generalization", {})
        .get("verdict")
    )
    if verdict != "PASS":
        raise RuntimeError(f"frozen A3 evaluation is not PASS: {verdict}")

    fixture_entries: list[dict[str, Any]] = []
    for fixture in FIXTURES:
        source = repo / "artifacts" / str(fixture["filename"])
        if not source.is_file():
            raise RuntimeError(f"required A3 fixture missing: {source}")
        actual = sha256_file(source)
        expected = str(fixture["sha256"])
        if actual != expected:
            raise RuntimeError(
                f"A3 benchmark drift for {fixture['fixture_id']}: expected {expected}, got {actual}. "
                f"Frozen authority commit is {FROZEN_BENCHMARK_COMMIT}."
            )
        fixture_dir = pack / "fixtures" / str(fixture["fixture_id"])
        fixture_dir.mkdir(parents=True)
        target = fixture_dir / "input.hwpx"
        shutil.copy2(source, target)
        fixture_entries.append(
            {
                **fixture,
                "path": target.relative_to(pack).as_posix(),
                "size": target.stat().st_size,
                "role": "FRESH_CROSS_ARCHETYPE_FIRST_PASS",
            }
        )

    evidence_dir = pack / "benchmark-evidence"
    evidence_dir.mkdir()
    shutil.copy2(receipt_src, evidence_dir / receipt_src.name)
    shutil.copy2(evaluation_src, evidence_dir / evaluation_src.name)

    manifest = {
        "schema": SCHEMA,
        "phase": PHASE,
        "source": {
            "repository": "https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP.git",
            "runner_commit": source_commit,
            "tracked_tree_clean": True,
            "generator_inputs": [
                {"path": p, "sha256": sha256_file(repo / p)} for p in GENERATOR_INPUTS
            ],
        },
        "benchmark_authority": {
            "benchmark": "AUTHORBENCH_A3_CROSS_ARCHETYPE",
            "frozen_commit": FROZEN_BENCHMARK_COMMIT,
            "workflow_run": 36186044354,
            "evaluation_verdict": verdict,
            "first_pass_artifact_id": 10885019734,
            "adjudication_artifact_id": 10885129628,
            "hash_lock": "EXACT_SHA256_REQUIRED",
        },
        "materialized_at_utc": utc_now(),
        "fixtures": fixture_entries,
        "capture_contract": {
            "renderer": "Hancom Hangul",
            "pdf_backend": "Hancom SaveAs PDF",
            "rasterizer": "PyMuPDF",
            "required": [
                "renderer_version",
                "hwp_executable_sha256",
                "dpi",
                "page_raster_sha256",
                "font_inventory",
                "page_composition_diagnostic",
                "custody",
            ],
            "authority": "NATIVE_RENDER_PAGE_COMPOSITION_OBSERVATION_NOT_HUMAN_DESIGN_VERDICT",
        },
    }
    write_json(pack / "capture-ready-manifest.json", manifest)
    return manifest


def _fixture(manifest: dict[str, Any], fixture_id: str) -> dict[str, Any]:
    fixture = next(
        (x for x in manifest.get("fixtures", []) if x.get("fixture_id") == fixture_id),
        None,
    )
    if fixture is None:
        raise RuntimeError(f"unknown fixture id: {fixture_id}")
    return fixture


def verify_fixture(pack: Path, fixture: dict[str, Any]) -> Path:
    path = pack / str(fixture["path"])
    if not path.is_file():
        raise RuntimeError(f"fixture missing: {path}")
    actual = sha256_file(path)
    if actual != fixture["sha256"]:
        raise RuntimeError(
            f"fixture hash mismatch for {fixture['fixture_id']}: "
            f"expected {fixture['sha256']}, got {actual}"
        )
    return path


def capture_pdf(
    *,
    pack: Path,
    fixture_id: str,
    pdf: Path,
    hancom_version: str,
    hancom_sha256: str,
    dpi: int,
    runner_sha256: str,
) -> dict[str, Any]:
    from scripts.p313r1_pdf_capture import page_capture

    manifest = read_json(pack / "capture-ready-manifest.json")
    fixture = _fixture(manifest, fixture_id)
    verify_fixture(pack, fixture)
    if not pdf.is_file() or pdf.stat().st_size <= 0:
        raise RuntimeError(f"missing or empty Hancom PDF: {pdf}")

    capture_dir = pack / "fixtures" / fixture_id / "capture"
    capture_dir.mkdir(parents=True, exist_ok=True)
    capture, fonts = page_capture(pdf, "page", capture_dir, dpi)
    if not capture.get("pages"):
        raise RuntimeError(f"Hancom PDF has no pages: {pdf}")

    renderer = {
        "name": "Hancom Hangul",
        "version": hancom_version,
        "hancom_native": True,
        "executable_sha256": hancom_sha256.lower(),
        "os": "Windows",
        "dpi": dpi,
        "pdf_backend": "Hancom SaveAs PDF",
        "rasterizer": "PyMuPDF",
    }
    diagnostic = diagnose_page_composition(
        capture,
        renderer=renderer,
        archetype=str(fixture["archetype"]),
    )
    if not diagnostic.get("world_contact_valid"):
        raise RuntimeError("P3.41 page-composition diagnostic rejected native world-contact authority")

    font_payload = {
        "schema": "chatgpt-web-hwpx-mcp/font-inventory/p3.41-r1/v1",
        "fixture_id": fixture_id,
        "fonts": fonts,
        "authority": "HANCOM_PDF_OBSERVED_FONT_INVENTORY",
    }
    write_json(capture_dir / "fonts.json", font_payload)
    write_json(capture_dir / "page-composition-diagnostic.json", diagnostic)

    receipt = {
        "schema": "chatgpt-web-hwpx-mcp/render-receipt/p3.41-r1/v1",
        "phase": PHASE,
        "fixture_id": fixture_id,
        "archetype": fixture["archetype"],
        "source_commit": manifest["source"]["runner_commit"],
        "benchmark_frozen_commit": manifest["benchmark_authority"]["frozen_commit"],
        "source_sha256": fixture["sha256"],
        "source_size": fixture["size"],
        "pdf_sha256": sha256_file(pdf),
        "renderer": renderer,
        "capture": capture,
        "font_inventory": "fonts.json",
        "page_composition": {
            "diagnostic": "page-composition-diagnostic.json",
            "diagnostic_sha256": sha256_file(capture_dir / "page-composition-diagnostic.json"),
            "verdict": diagnostic["verdict"],
            "finding_count": diagnostic["finding_count"],
            "authority": diagnostic["authority"],
        },
        "custody": {
            "capture_ready_manifest_sha256": sha256_file(pack / "capture-ready-manifest.json"),
            "runner_sha256": runner_sha256.lower(),
            "captured_at_utc": utc_now(),
            "authority": "NATIVE_HANCOM_PAGE_COMPOSITION_OBSERVATION",
        },
    }
    write_json(capture_dir / "render-receipt.json", receipt)
    return receipt


def validate_complete(pack: Path) -> dict[str, Any]:
    manifest = read_json(pack / "capture-ready-manifest.json")
    failures: list[dict[str, str]] = []
    receipts: list[dict[str, Any]] = []
    for fixture in manifest.get("fixtures", []):
        fixture_id = str(fixture["fixture_id"])
        try:
            verify_fixture(pack, fixture)
            capture_dir = pack / "fixtures" / fixture_id / "capture"
            receipt_path = capture_dir / "render-receipt.json"
            diagnostic_path = capture_dir / "page-composition-diagnostic.json"
            receipt = read_json(receipt_path)
            diagnostic = read_json(diagnostic_path)
            if receipt.get("source_sha256") != fixture["sha256"]:
                raise RuntimeError("receipt source hash does not match frozen fixture")
            if not receipt.get("capture", {}).get("pages"):
                raise RuntimeError("receipt contains no page raster evidence")
            if diagnostic.get("authority") != "HANCOM_NATIVE_RENDER_EVIDENCE":
                raise RuntimeError("page-composition diagnostic lacks native Hancom authority")
            if not diagnostic.get("world_contact_valid"):
                raise RuntimeError("page-composition diagnostic world-contact is invalid")
            receipts.append(
                {
                    "fixture_id": fixture_id,
                    "archetype": fixture["archetype"],
                    "receipt_sha256": sha256_file(receipt_path),
                    "diagnostic_sha256": sha256_file(diagnostic_path),
                    "page_count": diagnostic["page_count"],
                    "verdict": diagnostic["verdict"],
                    "finding_count": diagnostic["finding_count"],
                }
            )
        except Exception as exc:
            failures.append({"fixture_id": fixture_id, "error": str(exc)})
    return {
        "schema": "authorbench/p341r1-capture-validation/v1",
        "phase": PHASE,
        "complete": not failures,
        "receipts": receipts,
        "failures": failures,
        "authority": (
            "NATIVE_HANCOM_A3_PAGE_COMPOSITION_COMPLETE"
            if not failures
            else "INCOMPLETE_NATIVE_WORLD_CONTACT"
        ),
    }


__all__ = [
    "FROZEN_BENCHMARK_COMMIT",
    "FIXTURES",
    "capture_pdf",
    "deterministic_zip",
    "materialize",
    "validate_complete",
    "write_json",
]
