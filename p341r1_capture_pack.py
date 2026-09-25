from __future__ import annotations

import base64
import hashlib
import io
import json
import shutil
import zipfile
from pathlib import Path, PurePosixPath
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
FROZEN_WORKFLOW_RUN = 36186044354
FROZEN_FIRST_PASS_ARTIFACT_ID = 10885019734
FROZEN_ADJUDICATION_ARTIFACT_ID = 10885129628
FROZEN_MATERIALIZATION_METHOD = "REPOSITORY_SEALED_WORKFLOW_ARTIFACT_BYTES_EXACT_SHA256"
FROZEN_ARTIFACT_SHARDS = tuple(
    f"benchmarks/frozen/p341/authorbench-a3-p341-first-pass.zip.b64.{index:02d}"
    for index in range(4)
)

FIXTURES = (
    {
        "fixture_id": "AUTHORBENCH_A3_RESEARCH_BRIEF",
        "filename": "authorbench-a3-research-brief.hwpx",
        "archetype": "RESEARCH_BRIEF",
        "sha256": "de7ae36c3f6d1602f1b8f6f846349ac8737b5c2e33b918b2d96a4ad7b9974555",
        "content_sha256": "cdd6584584fa8201bc780d0ce91bcd257e12155bdeb37391063d3a3cc7a53e87",
    },
    {
        "fixture_id": "AUTHORBENCH_A3_INSTITUTIONAL_REPORT",
        "filename": "authorbench-a3-institutional-report.hwpx",
        "archetype": "INSTITUTIONAL_REPORT",
        "sha256": "bc14b5a8b13bf473c2ad0b484d3b8b7a16accb8b8b8359853fdb221dddd5bcff",
        "content_sha256": "7778d251642cfc3e34f2491b038668f653168f599952ecb6d772bdf8bd373dcf",
    },
    {
        "fixture_id": "AUTHORBENCH_A3_ACADEMIC_REPORT",
        "filename": "authorbench-a3-academic-report.hwpx",
        "archetype": "ACADEMIC_REPORT",
        "sha256": "32b42461d4645b8db417b06b9db0518539900afc39e39ea39f2f7c501e023163",
        "content_sha256": "f027816f7666d5b553a80857ba5123ea33b91ba5585f1d4c94df0fb29da2353b",
    },
)

RUNNER_INPUTS = (
    "p341r1_capture_pack.py",
    "scripts/p341r1_materialize_capture_pack.py",
    "scripts/p341r1_capture_pdf.py",
    "scripts/p341r1_finalize_capture_pack.py",
    "scripts/p341r1_run_authorbench_hancom_capture.ps1",
    "scripts/common/HancomExport.ps1",
)


def hwpx_content_sha256(path: Path) -> str:
    """Hash HWPX package content while ignoring ZIP-container metadata such as timestamps."""
    with zipfile.ZipFile(path, "r") as archive:
        rows = []
        for name in sorted(archive.namelist()):
            payload = archive.read(name)
            rows.append(
                {
                    "name": name,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size": len(payload),
                }
            )
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_frozen_artifact_bytes(repo: Path) -> bytes:
    encoded_parts: list[str] = []
    for relative in FROZEN_ARTIFACT_SHARDS:
        path = repo / relative
        if not path.is_file():
            raise RuntimeError(f"sealed frozen A3 artifact shard missing: {relative}")
        encoded_parts.append("".join(path.read_text(encoding="ascii").split()))
    try:
        payload = base64.b64decode("".join(encoded_parts), validate=True)
    except Exception as exc:
        raise RuntimeError(f"sealed frozen A3 artifact base64 is invalid: {exc}") from exc
    actual = hashlib.sha256(payload).hexdigest()
    if actual != FROZEN_ARTIFACT_CONTAINER_SHA256:
        raise RuntimeError(
            "sealed frozen A3 workflow artifact SHA-256 mismatch: "
            f"expected {FROZEN_ARTIFACT_CONTAINER_SHA256}, got {actual}"
        )
    if not payload.startswith(b"PK"):
        raise RuntimeError("sealed frozen A3 workflow artifact is not a ZIP archive")
    return payload


def _unique_member(archive: zipfile.ZipFile, basename: str) -> str:
    matches = [
        name
        for name in archive.namelist()
        if not name.endswith("/") and PurePosixPath(name).name == basename
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"sealed frozen A3 artifact must contain exactly one {basename}; found {len(matches)}"
        )
    return matches[0]


def materialize(repo: Path, pack: Path) -> dict[str, Any]:
    repo = repo.resolve()
    pack = pack.resolve()
    if pack.exists():
        raise FileExistsError(f"refusing to overwrite existing run directory: {pack}")
    source_commit = assert_clean_source(repo)
    pack.mkdir(parents=True)

    # Fresh benchmark authority is the original workflow artifact bytes, not a
    # later execution of historical source code under a changed dependency/runtime
    # environment. The artifact was sealed into the repository as base64 shards.
    artifact_bytes = _read_frozen_artifact_bytes(repo)
    artifact_container_sha256 = hashlib.sha256(artifact_bytes).hexdigest()

    fixture_entries: list[dict[str, Any]] = []
    evidence_dir = pack / "benchmark-evidence"
    evidence_dir.mkdir()

    with zipfile.ZipFile(io.BytesIO(artifact_bytes), "r") as archive:
        receipt_member = _unique_member(archive, "authorbench-a3-receipt.json")
        receipt_bytes = archive.read(receipt_member)
        receipt = json.loads(receipt_bytes.decode("utf-8"))
        if receipt.get("schema") != "authorbench/a3/p341/v1":
            raise RuntimeError(f"unexpected frozen A3 receipt schema: {receipt.get('schema')}")
        receipt_cases = {str(x.get("id")): x for x in (receipt.get("cases") or [])}

        for fixture in FIXTURES:
            member = _unique_member(archive, str(fixture["filename"]))
            payload = archive.read(member)
            actual = hashlib.sha256(payload).hexdigest()
            expected = str(fixture["sha256"])
            if actual != expected:
                raise RuntimeError(
                    f"sealed frozen A3 SHA-256 mismatch for {fixture['fixture_id']}: "
                    f"expected {expected}, got {actual}"
                )

            fixture_dir = pack / "fixtures" / str(fixture["fixture_id"])
            fixture_dir.mkdir(parents=True)
            target = fixture_dir / "input.hwpx"
            target.write_bytes(payload)

            actual_content_sha256 = hwpx_content_sha256(target)
            expected_content_sha256 = str(fixture["content_sha256"])
            if actual_content_sha256 != expected_content_sha256:
                raise RuntimeError(
                    f"sealed frozen A3 package-content mismatch for {fixture['fixture_id']}: "
                    f"expected {expected_content_sha256}, got {actual_content_sha256}"
                )

            case_id = str(fixture["filename"]).removeprefix("authorbench-a3-").removesuffix(".hwpx")
            receipt_case = receipt_cases.get(case_id)
            if not receipt_case:
                raise RuntimeError(f"frozen receipt is missing case {case_id}")
            if str(receipt_case.get("sha256")) != expected:
                raise RuntimeError(
                    f"frozen receipt SHA-256 disagrees with custody lock for {fixture['fixture_id']}"
                )

            fixture_entries.append(
                {
                    "fixture_id": fixture["fixture_id"],
                    "filename": fixture["filename"],
                    "archetype": fixture["archetype"],
                    "path": target.relative_to(pack).as_posix(),
                    "size": target.stat().st_size,
                    "sha256": actual,
                    "content_sha256": actual_content_sha256,
                    "frozen_artifact_sha256": expected,
                    "role": "FROZEN_FRESH_EXACT_ARTIFACT_BYTES",
                }
            )

        (evidence_dir / "authorbench-a3-receipt.json").write_bytes(receipt_bytes)
        frozen_members = sorted(
            name for name in archive.namelist() if not name.endswith("/")
        )

    authority_receipt = {
        "schema": "authorbench/a3/p341-frozen-authority/v1",
        "frozen_commit": FROZEN_BENCHMARK_COMMIT,
        "workflow_run": FROZEN_WORKFLOW_RUN,
        "first_pass_artifact_id": FROZEN_FIRST_PASS_ARTIFACT_ID,
        "adjudication_artifact_id": FROZEN_ADJUDICATION_ARTIFACT_ID,
        "first_pass_static_adjudication": "PASS",
        "authority": "FRESH_FIRST_PASS_STATIC_AND_NATIVE_STRUCTURE_BEFORE_A3_RENDER_CONTACT",
        "artifact_container_sha256": artifact_container_sha256,
        "materialization_method": FROZEN_MATERIALIZATION_METHOD,
    }
    write_json(evidence_dir / "frozen-authority.json", authority_receipt)

    manifest = {
        "schema": SCHEMA,
        "phase": PHASE,
        "source": {
            "repository": "https://github.com/WhoSia/ChatGPT-Web-HWPX-MCP.git",
            "runner_commit": source_commit,
            "tracked_tree_clean": True,
            "runner_inputs": [
                {"path": p, "sha256": sha256_file(repo / p)} for p in RUNNER_INPUTS
            ],
            "frozen_artifact_shards": [
                {"path": p, "sha256": sha256_file(repo / p)} for p in FROZEN_ARTIFACT_SHARDS
            ],
        },
        "benchmark_authority": {
            "benchmark": "AUTHORBENCH_A3_CROSS_ARCHETYPE",
            "frozen_commit": FROZEN_BENCHMARK_COMMIT,
            "workflow_run": FROZEN_WORKFLOW_RUN,
            "evaluation_verdict": "PASS",
            "first_pass_artifact_id": FROZEN_FIRST_PASS_ARTIFACT_ID,
            "adjudication_artifact_id": FROZEN_ADJUDICATION_ARTIFACT_ID,
            "artifact_container_sha256": artifact_container_sha256,
            "artifact_member_count": len(frozen_members),
            "original_artifact_hash_lock": "EXACT_SHA256",
            "capture_replay_gate": "EXACT_ORIGINAL_HWPX_SHA256_AND_PACKAGE_CONTENT_SHA256",
            "materialization_method": FROZEN_MATERIALIZATION_METHOD,
            "freshness_role": "ORIGINAL_FIRST_COMPLETED_A3_ARTIFACT_BYTES",
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
        "benchmark_frozen_artifact_sha256": fixture.get("frozen_artifact_sha256"),
        "benchmark_content_sha256": fixture.get("content_sha256"),
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
    "FROZEN_ARTIFACT_CONTAINER_SHA256",
    "FROZEN_ARTIFACT_SHARDS",
    "FROZEN_BENCHMARK_COMMIT",
    "FROZEN_MATERIALIZATION_METHOD",
    "FIXTURES",
    "capture_pdf",
    "deterministic_zip",
    "materialize",
    "validate_complete",
    "hwpx_content_sha256",
    "write_json",
]
