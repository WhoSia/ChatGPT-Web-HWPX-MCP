from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

PHASE = "P4.14"
PRODUCT = "0.39.0-p4.14"
SCHEMA = "chatgpt-web-hwpx-mcp/p414/distributed-native-capture/v1"
PROTOCOL_VERSION = "1.0"
AGENT_VERSION = "1.0.0"
BASELINE_HEAD = "adeb06e6f55fbc0b7116e998ebbfe3ed18811754"
BASELINE_PRODUCT = "0.38.0-p4.13"
BASELINE_DEPLOY = "dep-davkg0vavr4c73cd4j30"
BASELINE_NATIVE_HEAD = "da77daa9c3d21fffb37a0e3b600f46205e8de6f1"
ROOT = Path(__file__).resolve().parent
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def capture_agent_contract() -> dict:
    result = {
        "phase": PHASE,
        "product": PRODUCT,
        "schema": SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "agent_version": AGENT_VERSION,
        "job_fields": ["job_id", "exact_head", "product", "source_manifest", "source_manifest_sha256", "hancom_build_expected", "issued_at", "expires_at", "nonce", "output_target", "capture_kind", "document_binding"],
        "receipt_fields": ["agent_id", "key_id", "signed_payload", "signature_ed25519_b64", "canonical_sha256"],
        "source_access": "DECLARED_JOB_MANIFEST_ONLY; NO_WATCHER; NO_RECURSIVE_SCAN",
        "process_custody": "ONLY_HWP_PIDS_CREATED_BY_THIS_JOB_MAY_BE_CLOSED_OR_TERMINATED; NEVER_GLOBAL_KILL",
        "retry_semantics": "EXACT_COMPLETED_RECEIPT_RETRY_IS_IDEMPOTENT; ALTERED_REPLAY_REJECTED; INTERRUPTED_JOB_EMITS_RECOVERY_RECEIPT",
        "signing": "ED25519_PRIVATE_KEY_LOCAL_TO_CAPTURE_AGENT; SERVER_STORES_PUBLIC_KEYS_ONLY",
        "authority": "P414_CAPTURE_AGENT_PROTOCOL_CONTRACT",
    }
    result["contract_sha256"] = canonical_sha256(result)
    return result


def validate_source_manifest(manifest: Any) -> list[dict]:
    issues: list[dict] = []
    if not isinstance(manifest, Mapping):
        return [{"code": "SOURCE_MANIFEST_NOT_OBJECT"}]
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        issues.append({"code": "SOURCE_MANIFEST_EMPTY"})
        return issues
    seen: set[str] = set()
    for row in files:
        if not isinstance(row, Mapping):
            issues.append({"code": "SOURCE_ENTRY_NOT_OBJECT"})
            continue
        rel = str(row.get("path") or "")
        path = PurePosixPath(rel.replace("\\", "/"))
        if not rel or path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0].endswith(":"):
            issues.append({"code": "UNSAFE_SOURCE_PATH", "path": rel})
        if rel in seen:
            issues.append({"code": "DUPLICATE_SOURCE_PATH", "path": rel})
        seen.add(rel)
        if not _HEX64.fullmatch(str(row.get("sha256") or "").lower()):
            issues.append({"code": "INVALID_SOURCE_SHA256", "path": rel})
        try:
            if int(row.get("bytes")) < 1:
                raise ValueError
        except (TypeError, ValueError):
            issues.append({"code": "INVALID_SOURCE_SIZE", "path": rel})
        if not str(row.get("fixture_id") or "").strip() or not str(row.get("lowering_family") or "").strip():
            issues.append({"code": "SOURCE_IDENTITY_INCOMPLETE", "path": rel})
    return issues


def validate_capture_job(job: Mapping[str, Any], *, now: datetime | None = None, expected_head: str | None = None) -> dict:
    issues = []
    required = ("job_id", "exact_head", "product", "source_root", "source_manifest", "source_manifest_sha256", "hancom_build_expected", "issued_at", "expires_at", "nonce", "output_target", "capture_kind")
    missing = [key for key in required if job.get(key) in (None, "")]
    if missing:
        issues.append({"code": "MISSING_REQUIRED_FIELDS", "fields": missing})
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,127}", str(job.get("job_id") or "")):
        issues.append({"code": "INVALID_JOB_ID"})
    if not _HEX40.fullmatch(str(job.get("exact_head") or "").lower()):
        issues.append({"code": "INVALID_EXACT_HEAD"})
    if expected_head and str(job.get("exact_head") or "").lower() != expected_head.lower():
        issues.append({"code": "EXACT_HEAD_MISMATCH", "expected": expected_head})
    if job.get("product") != PRODUCT:
        issues.append({"code": "PRODUCT_MISMATCH", "expected": PRODUCT})
    manifest = job.get("source_manifest")
    issues.extend(validate_source_manifest(manifest))
    if isinstance(manifest, Mapping) and job.get("source_manifest_sha256") != canonical_sha256(manifest):
        issues.append({"code": "SOURCE_MANIFEST_HASH_MISMATCH"})
    nonce = str(job.get("nonce") or "")
    if len(nonce) < 22 or len(nonce) > 256 or any(ord(c) < 33 or ord(c) > 126 for c in nonce):
        issues.append({"code": "INVALID_NONCE"})
    if not str(job.get("hancom_build_expected") or "").strip():
        issues.append({"code": "HANCOM_BUILD_REQUIRED"})
    root = str(job.get("source_root") or "")
    target = str(job.get("output_target") or "")
    if root and target and _same_or_nested_path(root, target):
        issues.append({"code": "OUTPUT_MUST_BE_OUTSIDE_SOURCE_ROOT"})
    try:
        issued = _parse_time(job.get("issued_at"))
        expires = _parse_time(job.get("expires_at"))
        clock = now or datetime.now(timezone.utc)
        if expires <= issued:
            issues.append({"code": "INVALID_EXPIRY_WINDOW"})
        if expires - issued > timedelta(hours=12):
            issues.append({"code": "JOB_TTL_TOO_LONG"})
        if issued > clock + timedelta(minutes=5):
            issues.append({"code": "ISSUED_IN_FUTURE"})
        if expires <= clock:
            issues.append({"code": "JOB_EXPIRED"})
    except (TypeError, ValueError, OverflowError):
        issues.append({"code": "INVALID_JOB_TIMESTAMP"})
    result = {"phase": PHASE, "status": "PASS" if not issues else "FAIL", "issues": issues, "job_id": job.get("job_id"), "exact_head": job.get("exact_head"), "source_manifest_sha256": job.get("source_manifest_sha256"), "authority": "P414_CAPTURE_JOB_VALIDATOR"}
    result["validation_sha256"] = canonical_sha256(result)
    return result


def _same_or_nested_path(root: str, target: str) -> bool:
    import ntpath
    r = ntpath.normcase(ntpath.abspath(root))
    t = ntpath.normcase(ntpath.abspath(target))
    try:
        return ntpath.commonpath([r, t]) == r
    except ValueError:
        return False


def _parse_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO-8601 string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must carry a timezone")
    return parsed.astimezone(timezone.utc)


def verify_signed_receipt(receipt: Mapping[str, Any], key_registry: Mapping[str, Any], *, now: datetime | None = None, expected_head: str | None = None, allow_test_receipts: bool = False) -> dict:
    issues: list[dict] = []
    agent_id = str(receipt.get("agent_id") or "")
    key_id = str(receipt.get("key_id") or "")
    payload = receipt.get("signed_payload")
    signature_b64 = str(receipt.get("signature_ed25519_b64") or "")
    digest = canonical_sha256(payload) if isinstance(payload, Mapping) else ""
    if receipt.get("schema") != SCHEMA:
        issues.append({"code": "SCHEMA_MISMATCH"})
    key = key_registry.get(key_id)
    if not isinstance(key, Mapping) or key.get("agent_id") != agent_id:
        issues.append({"code": "UNKNOWN_OR_WRONG_KEY"})
    elif key.get("status", "ACTIVE") != "ACTIVE" or key.get("revoked_at"):
        issues.append({"code": "KEY_NOT_ACTIVE"})
    if not isinstance(payload, Mapping):
        issues.append({"code": "SIGNED_PAYLOAD_NOT_OBJECT"})
    else:
        if receipt.get("canonical_sha256") != digest:
            issues.append({"code": "CANONICAL_DIGEST_MISMATCH"})
        if payload.get("schema") != SCHEMA or payload.get("protocol_version") != PROTOCOL_VERSION:
            issues.append({"code": "PROTOCOL_MISMATCH"})
        if payload.get("product") != PRODUCT:
            issues.append({"code": "PRODUCT_MISMATCH"})
        if payload.get("test_only") is True and not allow_test_receipts:
            issues.append({"code": "TEST_RECEIPTS_DISABLED"})
        if expected_head and payload.get("exact_head") != expected_head:
            issues.append({"code": "EXACT_HEAD_MISMATCH"})
        for field in ("job_id", "source_manifest_sha256", "source_manifest", "hancom_version", "hancom_build", "capture_agent_version", "issued_at", "expires_at", "nonce", "source_files", "outputs", "process_custody"):
            if payload.get(field) in (None, ""):
                issues.append({"code": "MISSING_SIGNED_FIELD", "field": field})
        try:
            issued, expires = _parse_time(payload.get("issued_at")), _parse_time(payload.get("expires_at"))
            clock = now or datetime.now(timezone.utc)
            if expires <= issued or expires - issued > timedelta(hours=12):
                issues.append({"code": "INVALID_SIGNED_EXPIRY"})
            if issued > clock + timedelta(minutes=5):
                issues.append({"code": "SIGNED_ISSUED_IN_FUTURE"})
            if expires <= clock:
                issues.append({"code": "SIGNED_RECEIPT_EXPIRED"})
        except (TypeError, ValueError, OverflowError):
            issues.append({"code": "INVALID_SIGNED_TIMESTAMP"})
        if not _HEX40.fullmatch(str(payload.get("exact_head") or "").lower()):
            issues.append({"code": "INVALID_EXACT_HEAD"})
        if not _HEX64.fullmatch(str(payload.get("source_manifest_sha256") or "").lower()):
            issues.append({"code": "INVALID_SOURCE_MANIFEST_HASH"})
        source_manifest = payload.get("source_manifest")
        if isinstance(source_manifest, Mapping) and canonical_sha256(source_manifest) != payload.get("source_manifest_sha256"):
            issues.append({"code": "SIGNED_SOURCE_MANIFEST_HASH_MISMATCH"})
        if payload.get("capture_status") not in {"CAPTURED", "FAILED"}:
            issues.append({"code": "INVALID_CAPTURE_STATUS"})
        if payload.get("capture_status") in {"PASS", "CAPTURED"}:
            sources = payload.get("source_files") if isinstance(payload.get("source_files"), list) else []
            outputs = payload.get("outputs") if isinstance(payload.get("outputs"), list) else []
            if not sources or not outputs or any(not isinstance(x, Mapping) or not _HEX64.fullmatch(str(x.get("pdf_sha256") or "").lower()) for x in outputs):
                issues.append({"code": "NATIVE_CAPTURE_WITHOUT_PDF_HASH"})
            if any(not isinstance(x, Mapping) or x.get("export_succeeded") is not True or not isinstance(x.get("page_count"), int) or x.get("page_count") < 1 or not isinstance(x.get("bytes"), int) or x.get("bytes") < 1 for x in outputs):
                issues.append({"code": "NATIVE_PDF_EXPORT_RECEIPT_INCOMPLETE"})
            if any(not isinstance(x, Mapping) or x.get("unchanged_after_capture") is not True or not _HEX64.fullmatch(str(x.get("sha256") or "").lower()) for x in sources):
                issues.append({"code": "NATIVE_CAPTURE_SOURCE_CUSTODY_INCOMPLETE"})
            if not _HEX64.fullmatch(str(payload.get("capture_manifest_sha256") or "").lower()):
                issues.append({"code": "CAPTURE_MANIFEST_HASH_REQUIRED"})
            if not isinstance(payload.get("process_custody"), Mapping) or payload.get("process_custody", {}).get("global_kill_used") is not False:
                issues.append({"code": "PROCESS_CUSTODY_REQUIRED_OR_GLOBAL_KILL_DETECTED"})
            if payload.get("visual_verdict") not in {"PASS", "PASS_WITH_RESIDUALS", "FAIL", "PENDING"}:
                issues.append({"code": "INVALID_VISUAL_VERDICT"})
            if payload.get("hancom_version") in (None, "") or payload.get("hancom_build") in (None, ""):
                issues.append({"code": "NATIVE_PASS_WITHOUT_HANCOM_IDENTITY"})
            if not _HEX64.fullmatch(str(payload.get("hancom_executable_sha256") or "").lower()):
                issues.append({"code": "HANCOM_EXECUTABLE_HASH_REQUIRED"})
            if not payload.get("windows_version") or not payload.get("windows_build"):
                issues.append({"code": "WINDOWS_BUILD_IDENTITY_REQUIRED"})
            expected_sources = {str(x.get("fixture_id")): x for x in (source_manifest.get("files", []) if isinstance(source_manifest, Mapping) else [])}
            actual_sources = {str(x.get("fixture_id")): x for x in sources if isinstance(x, Mapping)}
            if not expected_sources or set(expected_sources) != set(actual_sources):
                issues.append({"code": "CAPTURE_SOURCE_SET_MISMATCH"})
            else:
                for fixture_id, row in expected_sources.items():
                    if actual_sources[fixture_id].get("sha256") != row.get("sha256") or actual_sources[fixture_id].get("path") != row.get("path"):
                        issues.append({"code": "CAPTURE_SOURCE_IDENTITY_MISMATCH", "fixture_id": fixture_id})
            output_ids = {str(x.get("fixture_id")) for x in outputs if isinstance(x, Mapping) and x.get("export_succeeded") is True}
            if payload.get("visual_verdict") in {"PASS", "PASS_WITH_RESIDUALS"} and (payload.get("capture_status") != "CAPTURED" or output_ids != set(expected_sources) or any(x.get("export_succeeded") is not True for x in outputs if isinstance(x, Mapping))):
                issues.append({"code": "VISUAL_PASS_WITH_INCOMPLETE_CAPTURE"})
            if payload.get("visual_verdict") in {"PASS", "PASS_WITH_RESIDUALS"}:
                human = payload.get("visual_observations", {}).get("human_adjudications", []) if isinstance(payload.get("visual_observations"), Mapping) else []
                adjudicated = {str(x.get("fixture_id")) for x in human if isinstance(x, Mapping) and x.get("status") in {"PASS", "PASS_WITH_RESIDUALS"} and x.get("reviewer") and x.get("reviewed_at")}
                if not output_ids or not output_ids.issubset(adjudicated):
                    issues.append({"code": "HUMAN_VISUAL_ADJUDICATION_INCOMPLETE"})
        if payload.get("recovery_status") == "INTERRUPTED":
            issues.append({"code": "INTERRUPTED_JOB_NOT_CERTIFIABLE"})
    if isinstance(key, Mapping) and isinstance(payload, Mapping) and not any(i["code"] == "UNKNOWN_OR_WRONG_KEY" for i in issues):
        try:
            public_bytes = base64.b64decode(str(key.get("public_key_ed25519_b64") or ""), validate=True)
            signature = base64.b64decode(signature_b64, validate=True)
            if len(public_bytes) != 32 or len(signature) != 64:
                raise ValueError("invalid Ed25519 key/signature size")
            Ed25519PublicKey.from_public_bytes(public_bytes).verify(signature, canonical_json(payload))
        except (ValueError, binascii.Error, InvalidSignature):
            issues.append({"code": "SIGNATURE_INVALID"})
    result = {"phase": PHASE, "status": "PASS" if not issues else "REJECTED", "accepted": not issues, "agent_id": agent_id, "key_id": key_id, "job_id": payload.get("job_id") if isinstance(payload, Mapping) else None, "exact_head": payload.get("exact_head") if isinstance(payload, Mapping) else None, "nonce": payload.get("nonce") if isinstance(payload, Mapping) else None, "canonical_sha256": digest, "raw_receipt_sha256": canonical_sha256(receipt), "issues": issues, "authority": "P414_SIGNED_NATIVE_RECEIPT_VERIFIER"}
    result["validation_sha256"] = canonical_sha256(result)
    return result


def normalize_capture_evidence(receipt: Mapping[str, Any], validation: Mapping[str, Any]) -> dict:
    payload = receipt.get("signed_payload") if isinstance(receipt.get("signed_payload"), Mapping) else {}
    return {"agent_id": receipt.get("agent_id"), "key_id": receipt.get("key_id"), "job_id": payload.get("job_id"), "exact_head": payload.get("exact_head"), "product": payload.get("product"), "hancom_version": payload.get("hancom_version"), "hancom_build": payload.get("hancom_build"), "source_manifest_sha256": payload.get("source_manifest_sha256"), "capture_agent_version": payload.get("capture_agent_version"), "source_files": payload.get("source_files", []), "outputs": payload.get("outputs", []), "visual_verdict": payload.get("visual_verdict", "PENDING"), "visual_observations": payload.get("visual_observations", {}), "document_binding": payload.get("document_binding"), "capture_status": payload.get("capture_status"), "captured_at": payload.get("captured_at"), "test_only": payload.get("test_only") is True, "accepted": bool(validation.get("accepted")), "evidence_id": canonical_sha256(receipt)}


def release_identity_seed() -> dict:
    return {"release_id": "p413-adeb06e6-dep-davkg0vavr4c73cd4j30", "product": BASELINE_PRODUCT, "exact_head": BASELINE_HEAD, "render_service_id": "srv-daiimp8ae00c73em8tjg", "render_deploy_id": BASELINE_DEPLOY, "native_baseline_phase": "P4.12", "native_baseline_exact_head": BASELINE_NATIVE_HEAD, "native_baseline_authority": "RELEASE_BASELINE_NATIVE_AUTHORITY", "certification_status": "CERTIFIED", "inherited_not_rewritten": True}


def release_change_vectors(*, exact_head: str = "PENDING_EXACT_HEAD") -> tuple[dict, dict]:
    baseline = json.loads((ROOT / "benchmarks" / "p412_native_requalification.json").read_text(encoding="utf-8"))
    cases = [{"fixture_id": row["case_id"], "source_sha256": row["source_sha256"]} for row in sorted(baseline["cases"], key=lambda x: x["case_id"])]
    common = {
        "hancom_build": baseline["hancom"]["expected_version"],
        "lowering_families_sha256": canonical_sha256(["P4.8_SEMANTIC_COMPONENTS"]),
        "fixture_families_sha256": canonical_sha256([row["fixture_id"] for row in cases]),
        "source_fixture_manifest_sha256": canonical_sha256(cases),
    }
    previous = {"release_id": "p413-adeb06e6-dep-davkg0vavr4c73cd4j30", "product": BASELINE_PRODUCT, "exact_head": BASELINE_HEAD, **common, "capture_agent_protocol_version": "NO_DISTRIBUTED_AGENT/P4.13_SERVER_INGESTION_ONLY"}
    candidate = {"release_id": "p414-candidate-" + exact_head[:12], "product": PRODUCT, "exact_head": exact_head, **common, "capture_agent_protocol_version": PROTOCOL_VERSION, "capture_agent_version": AGENT_VERSION}
    return previous, candidate


def hancom_build_matrix(receipts: list[Mapping[str, Any]] | None = None) -> dict:
    cells = []
    for receipt in receipts or []:
        if not receipt.get("accepted") or receipt.get("test_only") is True:
            continue
        for fixture in receipt.get("source_files") or []:
            output = next((x for x in receipt.get("outputs", []) if x.get("fixture_id") == fixture.get("fixture_id")), {})
            visual = str(receipt.get("visual_verdict") or "PENDING")
            observations = receipt.get("visual_observations") if isinstance(receipt.get("visual_observations"), Mapping) else {}
            reviews = observations.get("human_adjudications") if isinstance(observations.get("human_adjudications"), list) else []
            blocking_review = any(set(x.get("defects") or []) & _BLOCKING_DEFECTS for x in reviews if isinstance(x, Mapping))
            status = "REGRESSION" if visual == "FAIL" or blocking_review else "CERTIFIED" if visual in {"PASS", "PASS_WITH_RESIDUALS"} else "HOLD"
            cells.append({"exact_head": receipt.get("exact_head"), "product": receipt.get("product"), "hancom_version": receipt.get("hancom_version"), "hancom_build": receipt.get("hancom_build"), "fixture_id": fixture.get("fixture_id"), "source_sha256": fixture.get("sha256"), "lowering_family": fixture.get("lowering_family"), "capture_agent_version": receipt.get("capture_agent_version"), "native_pdf_sha256": output.get("pdf_sha256"), "visual_verdict": visual, "status": status, "evidence_id": receipt.get("evidence_id")})
    certified = [c for c in cells if c["status"] == "CERTIFIED"]
    # Store reads are newest-first; preserve that order rather than comparing commit hashes lexically.
    baseline_build = json.loads((ROOT / "benchmarks" / "p412_native_requalification.json").read_text(encoding="utf-8"))["hancom"]["expected_version"]
    incompatible = sorted({str(c["hancom_build"]) for c in cells if c.get("hancom_build") != baseline_build})
    overall = "UNKNOWN" if not cells else "REGRESSION" if any(c["status"] == "REGRESSION" for c in cells) else "CERTIFIED" if all(c["status"] == "CERTIFIED" for c in cells) else "HOLD"
    result = {"phase": PHASE, "status": overall, "baseline_hancom_build": baseline_build, "incompatible_builds": incompatible, "incompatible_builds_are_not_inherited_or_auto_promoted": True, "index_dimensions": ["exact_head", "product", "hancom_version", "hancom_build", "fixture_id", "source_sha256", "lowering_family", "capture_agent_version", "native_pdf_sha256", "visual_verdict"], "cells": cells, "latest_certified_baseline": certified[0] if certified else None, "prior_certified_release": release_identity_seed(), "inherited_release_baseline_is_not_agent_cell": True, "authority": "P414_VERSION_INDEXED_HANCOM_BUILD_MATRIX"}
    result["matrix_sha256"] = canonical_sha256(result)
    return result


def evaluate_release_capture_obligation(*, previous: Mapping[str, Any], candidate: Mapping[str, Any], unresolved_drift: bool = False, explicit_high_risk: bool = False) -> dict:
    triggers = []
    pairs = [("HANCOM_BUILD_CHANGE", "hancom_build"), ("ACTIVE_VISUAL_LOWERING_FAMILY_CHANGE", "lowering_families_sha256"), ("SEMANTIC_FIXTURE_FAMILY_CHANGE", "fixture_families_sha256"), ("SOURCE_FIXTURE_HASH_CHANGE", "source_fixture_manifest_sha256"), ("CAPTURE_AGENT_PROTOCOL_CHANGE", "capture_agent_protocol_version")]
    for code, key in pairs:
        if previous.get(key) != candidate.get(key):
            triggers.append({"code": code, "previous": previous.get(key), "candidate": candidate.get(key)})
    if unresolved_drift:
        triggers.append({"code": "PREVIOUS_DRIFT_UNRESOLVED"})
    if explicit_high_risk:
        triggers.append({"code": "EXPLICIT_HIGH_RISK_RELEASE"})
    blocking = unresolved_drift or explicit_high_risk or any(x["code"] in {"HANCOM_BUILD_CHANGE", "ACTIVE_VISUAL_LOWERING_FAMILY_CHANGE", "SEMANTIC_FIXTURE_FAMILY_CHANGE", "SOURCE_FIXTURE_HASH_CHANGE"} for x in triggers)
    status = "NO_FRESH_CAPTURE_REQUIRED" if not triggers else "BLOCKING_CAPTURE_REQUIRED" if blocking else "FRESH_CAPTURE_REQUIRED"
    result = {"phase": PHASE, "status": status, "triggers": triggers, "previous_release": dict(previous), "candidate_release": dict(candidate), "blocks_promotion": status == "BLOCKING_CAPTURE_REQUIRED", "authority": "P414_RELEASE_TRIGGERED_CAPTURE_OBLIGATION"}
    result["obligation_sha256"] = canonical_sha256(result)
    return result


_BLOCKING_DEFECTS = {"SEMANTIC_DISAPPEARANCE", "VECTOR_ESCAPE", "CLIPPING", "OVERLAP", "BAR_VISIBILITY_REGRESSION", "KPI_VISIBILITY_REGRESSION", "NOVEL_DEFECT"}


def compare_native_visual_drift(baseline: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict:
    base_hashes = {x.get("fixture_id"): x.get("source_sha256") for x in baseline.get("cases", [])}
    issues = []
    for row in candidate.get("cases", []):
        fid = row.get("fixture_id")
        if fid in base_hashes and base_hashes[fid] != row.get("source_sha256"):
            issues.append({"code": "SOURCE_DRIFT", "fixture_id": fid, "severity": "REVIEW"})
        if row.get("pdf_sha256") != row.get("baseline_pdf_sha256"):
            issues.append({"code": "PDF_BYTE_DRIFT", "fixture_id": fid, "severity": "DIAGNOSTIC"})
        codes = set(row.get("defects") or [])
        if row.get("semantic_visible") is False:
            codes.add("SEMANTIC_DISAPPEARANCE")
        if row.get("vector_escape") is True:
            codes.add("VECTOR_ESCAPE")
        if row.get("clipping") is True:
            codes.add("CLIPPING")
        if row.get("overlap") is True:
            codes.add("OVERLAP")
        if row.get("bar_visible") is False:
            codes.add("BAR_VISIBILITY_REGRESSION")
        if row.get("kpi_visible") is False:
            codes.add("KPI_VISIBILITY_REGRESSION")
        for code in sorted(codes):
            issues.append({"code": code, "fixture_id": fid, "severity": "BLOCKING" if code in _BLOCKING_DEFECTS else "REVIEW"})
        if row.get("build_specific_expected_drift"):
            issues.append({"code": "BUILD_SPECIFIC_EXPECTED_DRIFT", "fixture_id": fid, "severity": "DIAGNOSTIC", "reference": row["build_specific_expected_drift"]})
    blocking = [x for x in issues if x["severity"] == "BLOCKING"]
    complete = candidate.get("capture_status") == "CAPTURED" and bool(candidate.get("cases")) and all(x.get("pdf_sha256") for x in candidate.get("cases", []))
    status = "BLOCKING_REGRESSION" if blocking else "NO_BLOCKING_DRIFT" if complete else "EVIDENCE_INCOMPLETE"
    result = {"phase": PHASE, "status": status, "evidence_complete": complete, "source_vs_render_drift_separated": True, "issues": issues, "blocking_count": len(blocking), "baseline_identity": baseline.get("release_identity"), "candidate_identity": candidate.get("release_identity"), "authority": "P414_TYPED_NATIVE_VISUAL_DRIFT_ADJUDICATION"}
    result["drift_receipt_sha256"] = canonical_sha256(result)
    return result


def compare_signed_receipt_to_promoted_baseline(receipt: Mapping[str, Any]) -> dict:
    baseline_data = json.loads((ROOT / "benchmarks" / "p412_native_requalification.json").read_text(encoding="utf-8"))
    baseline = {"release_identity": {"phase": baseline_data["phase"], "product": baseline_data["product"], "exact_head": baseline_data["exact_head"]}, "cases": baseline_data["cases"]}
    payload = receipt.get("signed_payload") if isinstance(receipt.get("signed_payload"), Mapping) else {}
    reviews = payload.get("visual_observations", {}).get("human_adjudications", []) if isinstance(payload.get("visual_observations"), Mapping) else []
    review_by_id = {str(x.get("fixture_id")): x for x in reviews if isinstance(x, Mapping)}
    outputs = {str(x.get("fixture_id")): x for x in payload.get("outputs", []) if isinstance(x, Mapping)}
    cases = []
    for source in payload.get("source_files", []):
        if not isinstance(source, Mapping):
            continue
        fid = str(source.get("fixture_id"))
        review = review_by_id.get(fid, {})
        output = outputs.get(fid, {})
        defects = list(review.get("defects") or [])
        if review.get("status") == "FAIL" and not defects:
            defects.append("NOVEL_DEFECT")
        case = {"fixture_id": fid, "source_sha256": source.get("sha256"), "pdf_sha256": output.get("pdf_sha256"), "baseline_pdf_sha256": next((x.get("pdf_sha256") for x in baseline_data["cases"] if x.get("case_id") == fid), None), "defects": defects}
        for name in ("semantic_visible", "bar_visible", "kpi_visible", "vector_escape", "clipping", "overlap", "build_specific_expected_drift"):
            if name in review:
                case[name] = review[name]
        cases.append(case)
    candidate = {"release_identity": {"product": payload.get("product"), "exact_head": payload.get("exact_head"), "hancom_build": payload.get("hancom_build"), "capture_agent_version": payload.get("capture_agent_version")}, "capture_status": payload.get("capture_status"), "cases": cases}
    return compare_native_visual_drift(baseline, candidate)


def evaluate_rollback_authority(*, signed_evidence_validation: Mapping[str, Any], drift_receipt: Mapping[str, Any], current_release: Mapping[str, Any], target_release: Mapping[str, Any], mode: str = "DRY_RUN", approval_ref: str = "") -> dict:
    issues = []
    if signed_evidence_validation.get("accepted") is not True:
        issues.append({"code": "SIGNED_NATIVE_EVIDENCE_REQUIRED"})
    if drift_receipt.get("status") != "BLOCKING_REGRESSION":
        issues.append({"code": "BLOCKING_VISUAL_REGRESSION_REQUIRED"})
    if not current_release.get("release_id") or not current_release.get("exact_head") or not current_release.get("render_deploy_id"):
        issues.append({"code": "CURRENT_RELEASE_IDENTITY_INCOMPLETE"})
    if current_release.get("product") != PRODUCT or current_release.get("exact_head") != signed_evidence_validation.get("exact_head"):
        issues.append({"code": "CURRENT_RELEASE_NOT_BOUND_TO_SIGNED_NATIVE_EVIDENCE"})
    if target_release.get("certification_status") != "CERTIFIED" or not target_release.get("release_id") or not target_release.get("exact_head") or not target_release.get("render_deploy_id"):
        issues.append({"code": "TARGET_NOT_CERTIFIED_RELEASE"})
    pinned = release_identity_seed()
    for field in ("release_id", "product", "exact_head", "render_service_id", "render_deploy_id", "native_baseline_phase", "native_baseline_exact_head"):
        if target_release.get(field) != pinned.get(field):
            issues.append({"code": "TARGET_RELEASE_IDENTITY_NOT_PINNED", "field": field})
    if target_release.get("release_id") == current_release.get("release_id"):
        issues.append({"code": "ROLLBACK_TARGET_EQUALS_CURRENT"})
    if mode not in {"DRY_RUN", "APPROVED_EXECUTION"}:
        issues.append({"code": "INVALID_ROLLBACK_MODE"})
    if mode == "APPROVED_EXECUTION" and not approval_ref.strip():
        issues.append({"code": "APPROVAL_REFERENCE_REQUIRED"})
    authorized = not issues
    result = {"phase": PHASE, "status": "DRY_RUN_AUTHORIZED" if authorized and mode == "DRY_RUN" else "APPROVED_EXECUTION_AUTHORIZED" if authorized else "DENIED", "authorized": authorized, "mode": mode, "current_release": dict(current_release), "target_release": dict(target_release), "evidence_id": signed_evidence_validation.get("evidence_id"), "drift_receipt_sha256": drift_receipt.get("drift_receipt_sha256"), "approval_ref": approval_ref if mode == "APPROVED_EXECUTION" else None, "issues": issues, "execution_performed": False, "authority": "P414_SIGNED_EVIDENCE_RELEASE_BOUND_ROLLBACK_AUTHORITY"}
    result["rollback_authority_sha256"] = canonical_sha256(result)
    return result


def document_native_trust_receipt(*, document_id: str, revision: int, sha256: str, evidence: Mapping[str, Any] | None = None, release_head: str | None = None) -> dict:
    bound_to_document = evidence is not None and evidence.get("document_binding") == {"document_id": document_id, "revision": int(revision), "document_sha256": sha256}
    bound_to_release = evidence is not None and evidence.get("product") == PRODUCT and release_head not in (None, "", "PENDING_EXACT_HEAD") and evidence.get("exact_head") == release_head
    native = evidence is not None and evidence.get("accepted") is True and evidence.get("test_only") is not True and evidence.get("capture_status") == "CAPTURED" and evidence.get("visual_verdict") in {"PASS", "PASS_WITH_RESIDUALS"} and bound_to_document and bound_to_release
    bound = evidence is not None and evidence.get("accepted") is True and evidence.get("test_only") is not True and bound_to_document and bound_to_release
    failed = bound and (evidence.get("capture_status") == "FAILED" or evidence.get("visual_verdict") == "FAIL")
    authority_class = "PER_DOCUMENT_NATIVE_VERIFIED" if native else "NATIVE_VERIFICATION_FAILED" if failed else "NATIVE_VERIFICATION_PENDING"
    result = {"phase": PHASE, "document_id": document_id, "revision": int(revision), "document_sha256": sha256, "release_product": PRODUCT, "release_head": release_head or "PENDING_EXACT_HEAD", "authority_class": authority_class, "evidence_receipt_id": evidence.get("evidence_id") if bound else None, "evidence_receipt_sha256": evidence.get("evidence_id") if bound else None, "hancom_build": evidence.get("hancom_build") if bound else None, "capture_timestamp": evidence.get("captured_at") if bound else None, "scope_and_limitations": "Exact document bytes/revision and exact release head only; not generalized to other documents or Hancom builds." if native else "Inherited release baseline is not per-document capture evidence." if not failed else "Native capture or human visual adjudication failed; this document is not verified.", "authority": "P414_PER_DOCUMENT_NATIVE_TRUST_RECEIPT" if native or failed else "P414_RELEASE_BASELINE_NOT_PER_DOCUMENT_NATIVE"}
    result["trust_receipt_sha256"] = canonical_sha256(result)
    return result


def evidence_service_health(*, store_mode: str, key_count: int, revoked_key_count: int, receipt_count: int, replay_rejection_count: int) -> dict:
    result = {"phase": PHASE, "product": PRODUCT, "status": "PASS" if store_mode.startswith("postgres") else "HOLD", "durable_store": store_mode, "agent_key_count": int(key_count), "revoked_key_count": int(revoked_key_count), "accepted_receipt_count": int(receipt_count), "replay_rejection_count": int(replay_rejection_count), "private_keys_present_on_server": False, "native_authority_without_signed_hancom_receipt": False, "authority": "P414_EVIDENCE_SERVICE_HEALTH"}
    result["health_sha256"] = canonical_sha256(result)
    return result
