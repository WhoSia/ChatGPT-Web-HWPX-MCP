from __future__ import annotations

import hashlib
import json
import os
import platform
import re
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Mapping, Sequence

PHASE = "P4.16"
PRODUCT = "0.41.0-p4.16"
PARENT_PRODUCT = "0.40.0-p4.15"
PARENT_HEAD = "76d43331f3998d62f6f2ddb885b290b336e563bb"
PARENT_RELEASE_AUTHORITY_SHA256 = "b6fcb775fd1367dfbc41fa3a58d6091496dd96e709ee39487b6ca247f31c7055"
SCHEMA = "chatgpt-web-hwpx-mcp/p416/generation-manifest/v1"
WITNESS_SCHEMA = "chatgpt-web-hwpx-mcp/p416/minimal-generation-witness/v1"

_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")

WITNESS_DEPENDENCIES = (
    "release",
    "intent_sha256",
    "plan_sha256",
    "tool_trace_sha256",
    "source_input_set_sha256",
    "runtime_components_sha256",
    "deterministic_parameters_sha256",
    "artifact_sha256",
)


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def normalize_structured_input(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(k): normalize_structured_input(value[k])
            for k in sorted(value, key=lambda x: str(x))
        }
    if isinstance(value, (list, tuple)):
        return [normalize_structured_input(x) for x in value]
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("non-finite numeric input is not canonicalizable")
        return value
    raise TypeError(f"unsupported manifest input type: {type(value).__name__}")


def normalize_metadata_label(value: str) -> str:
    return " ".join(str(value or "").strip().split())


def _hex64(value: str, field: str) -> str:
    v = str(value or "").lower()
    if not _HEX64.fullmatch(v):
        raise ValueError(f"{field} must be a 64-character lowercase hexadecimal sha256")
    return v


def _hex40(value: str, field: str) -> str:
    v = str(value or "").lower()
    if not _HEX40.fullmatch(v):
        raise ValueError(f"{field} must be a 40-character lowercase hexadecimal git sha")
    return v


def runtime_release_identity() -> dict:
    exact_head = (
        os.environ.get("P416_RELEASE_EXACT_HEAD")
        or os.environ.get("RENDER_GIT_COMMIT")
        or os.environ.get("GITHUB_SHA")
        or PARENT_HEAD
    ).strip().lower()
    _hex40(exact_head, "release.exact_head")
    authority_digest = (
        os.environ.get("P416_RELEASE_AUTHORITY_SHA256")
        or PARENT_RELEASE_AUTHORITY_SHA256
    ).strip().lower()
    _hex64(authority_digest, "release.authority_sha256")
    return {
        "product": PRODUCT,
        "exact_head": exact_head,
        "authority_sha256": authority_digest,
        "authority_scope": (
            "P4.16_RELEASE_AUTHORITY"
            if os.environ.get("P416_RELEASE_AUTHORITY_SHA256")
            else "P4.15_PARENT_AUTHORITY_BASELINE_UNTIL_P4.16_SEAL"
        ),
    }


def _normalize_tool_trace(tool_trace: Sequence[Mapping[str, Any]]) -> list[dict]:
    rows = []
    for i, raw in enumerate(tool_trace):
        if not isinstance(raw, Mapping):
            raise TypeError("tool_trace entries must be objects")
        tool = normalize_metadata_label(str(raw.get("tool") or ""))
        capability = normalize_metadata_label(str(raw.get("capability") or ""))
        if not tool:
            raise ValueError("tool_trace entry missing tool")
        operation_sha256 = raw.get("operation_sha256")
        if operation_sha256 is None:
            operation_sha256 = canonical_sha256(
                normalize_structured_input(raw.get("operation") or {})
            )
        rows.append(
            {
                "ordinal": i,
                "tool": tool,
                "capability": capability,
                "operation_sha256": _hex64(
                    str(operation_sha256), "tool_trace.operation_sha256"
                ),
            }
        )
    return rows


def _normalize_source_inputs(source_inputs: Sequence[Mapping[str, Any]]) -> list[dict]:
    rows = []
    for raw in source_inputs:
        if not isinstance(raw, Mapping):
            raise TypeError("source_inputs entries must be objects")
        digest = raw.get("sha256")
        if digest is None:
            if "value" not in raw:
                raise ValueError("source input requires sha256 or value")
            digest = canonical_sha256(normalize_structured_input(raw["value"]))
        rows.append(
            {
                "source_id": normalize_metadata_label(str(raw.get("source_id") or "")),
                "kind": normalize_metadata_label(str(raw.get("kind") or "")),
                "sha256": _hex64(str(digest), "source_inputs.sha256"),
            }
        )
    return sorted(rows, key=lambda x: (x["kind"], x["source_id"], x["sha256"]))


def minimal_sufficient_generation_witness(manifest: Mapping[str, Any]) -> dict:
    witness = {
        "schema": WITNESS_SCHEMA,
        "phase": PHASE,
        "dependencies": list(WITNESS_DEPENDENCIES),
        "release": normalize_structured_input(manifest.get("release") or {}),
        "intent_sha256": manifest.get("intent_sha256"),
        "plan_sha256": manifest.get("plan_sha256"),
        "tool_trace_sha256": manifest.get("tool_trace_sha256"),
        "source_input_set_sha256": manifest.get("source_input_set_sha256"),
        "runtime_components_sha256": manifest.get("runtime_components_sha256"),
        "deterministic_parameters_sha256": manifest.get(
            "deterministic_parameters_sha256"
        ),
        "artifact_sha256": manifest.get("artifact_sha256"),
    }
    witness["witness_sha256"] = canonical_sha256(witness)
    return witness


def compile_generation_manifest(
    *,
    intent: Mapping[str, Any],
    plan: Mapping[str, Any],
    capability_path: Sequence[str],
    tool_trace: Sequence[Mapping[str, Any]],
    source_inputs: Sequence[Mapping[str, Any]],
    runtime_components: Mapping[str, Any],
    deterministic_parameters: Mapping[str, Any],
    artifact_sha256: str,
    release: Mapping[str, Any] | None = None,
    parent_document: Mapping[str, Any] | None = None,
    native_evidence_refs: Sequence[Mapping[str, Any]] = (),
) -> dict:
    normalized_intent = normalize_structured_input(intent)
    normalized_plan = normalize_structured_input(plan)
    normalized_capabilities = [
        normalize_metadata_label(x) for x in capability_path
    ]
    if any(not x for x in normalized_capabilities):
        raise ValueError("capability_path contains an empty capability")

    normalized_trace = _normalize_tool_trace(tool_trace)
    normalized_sources = _normalize_source_inputs(source_inputs)
    normalized_runtime = normalize_structured_input(runtime_components)
    normalized_parameters = normalize_structured_input(deterministic_parameters)
    normalized_release = normalize_structured_input(
        dict(release or runtime_release_identity())
    )
    normalized_release["product"] = str(
        normalized_release.get("product") or PRODUCT
    )
    normalized_release["exact_head"] = _hex40(
        str(normalized_release.get("exact_head") or ""), "release.exact_head"
    )
    normalized_release["authority_sha256"] = _hex64(
        str(normalized_release.get("authority_sha256") or ""),
        "release.authority_sha256",
    )
    normalized_native = [
        normalize_structured_input(x) for x in native_evidence_refs
    ]

    manifest = {
        "schema": SCHEMA,
        "phase": PHASE,
        "product": PRODUCT,
        "release": normalized_release,
        "normalization_profile": {
            "mapping_keys": "SORTED",
            "sequence_order": "PRESERVED",
            "string_content": "EXACT",
            "metadata_labels": "TRIM_AND_COLLAPSE_WHITESPACE",
            "raw_private_inputs_stored": False,
        },
        "intent_sha256": canonical_sha256(normalized_intent),
        "plan_sha256": canonical_sha256(normalized_plan),
        "capability_path": normalized_capabilities,
        "capability_path_sha256": canonical_sha256(normalized_capabilities),
        "tool_trace": normalized_trace,
        "tool_trace_sha256": canonical_sha256(normalized_trace),
        "source_inputs": normalized_sources,
        "source_input_set_sha256": canonical_sha256(normalized_sources),
        "runtime_components": normalized_runtime,
        "runtime_components_sha256": canonical_sha256(normalized_runtime),
        "deterministic_parameters": normalized_parameters,
        "deterministic_parameters_sha256": canonical_sha256(
            normalized_parameters
        ),
        "artifact_sha256": _hex64(artifact_sha256, "artifact_sha256"),
        "parent_document": (
            normalize_structured_input(parent_document)
            if parent_document
            else None
        ),
        "native_evidence_refs": normalized_native,
        "native_evidence_status": (
            "PRESENT_UNADJUDICATED" if normalized_native else "ABSENT"
        ),
        "native_pass_inferred": False,
    }
    manifest["minimal_witness"] = minimal_sufficient_generation_witness(
        manifest
    )
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    return manifest


def compile_generation_manifest_for_file(path: str | Path, **kwargs: Any) -> dict:
    return compile_generation_manifest(
        artifact_sha256=file_sha256(path), **kwargs
    )


def verify_generation_manifest(
    manifest: Mapping[str, Any],
    *,
    artifact_sha256: str | None = None,
    expected_release: Mapping[str, Any] | None = None,
) -> dict:
    issues = []
    required = {
        "schema",
        "phase",
        "product",
        "release",
        "intent_sha256",
        "plan_sha256",
        "tool_trace",
        "tool_trace_sha256",
        "source_inputs",
        "source_input_set_sha256",
        "runtime_components",
        "runtime_components_sha256",
        "deterministic_parameters",
        "deterministic_parameters_sha256",
        "artifact_sha256",
        "minimal_witness",
        "manifest_sha256",
    }
    for field in sorted(required):
        if field not in manifest:
            issues.append({"code": "REQUIRED_FIELD_MISSING", "field": field})

    if (
        manifest.get("schema") != SCHEMA
        or manifest.get("phase") != PHASE
        or manifest.get("product") != PRODUCT
    ):
        issues.append({"code": "MANIFEST_IDENTITY_MISMATCH"})

    expected_manifest = dict(manifest)
    observed_manifest_digest = expected_manifest.pop("manifest_sha256", None)
    if observed_manifest_digest != canonical_sha256(expected_manifest):
        issues.append({"code": "MANIFEST_DIGEST_MISMATCH"})

    trace = (
        manifest.get("tool_trace")
        if isinstance(manifest.get("tool_trace"), list)
        else []
    )
    if manifest.get("tool_trace_sha256") != canonical_sha256(trace):
        issues.append({"code": "TOOL_TRACE_DIGEST_MISMATCH"})

    sources = (
        manifest.get("source_inputs")
        if isinstance(manifest.get("source_inputs"), list)
        else []
    )
    if manifest.get("source_input_set_sha256") != canonical_sha256(sources):
        issues.append({"code": "SOURCE_INPUT_SET_DIGEST_MISMATCH"})

    runtime = (
        manifest.get("runtime_components")
        if isinstance(manifest.get("runtime_components"), Mapping)
        else {}
    )
    if manifest.get("runtime_components_sha256") != canonical_sha256(runtime):
        issues.append({"code": "RUNTIME_COMPONENT_DIGEST_MISMATCH"})

    params = (
        manifest.get("deterministic_parameters")
        if isinstance(manifest.get("deterministic_parameters"), Mapping)
        else {}
    )
    if manifest.get("deterministic_parameters_sha256") != canonical_sha256(
        params
    ):
        issues.append({"code": "DETERMINISTIC_PARAMETER_DIGEST_MISMATCH"})

    witness = manifest.get("minimal_witness")
    if not isinstance(witness, Mapping):
        issues.append({"code": "MINIMAL_WITNESS_MISSING"})
    elif dict(witness) != minimal_sufficient_generation_witness(manifest):
        issues.append({"code": "MINIMAL_WITNESS_MISMATCH"})

    observed_artifact = str(manifest.get("artifact_sha256") or "").lower()
    if not _HEX64.fullmatch(observed_artifact):
        issues.append({"code": "INVALID_ARTIFACT_DIGEST"})
    if (
        artifact_sha256 is not None
        and observed_artifact != str(artifact_sha256).lower()
    ):
        issues.append({"code": "ARTIFACT_MANIFEST_BINDING_MISMATCH"})

    release_obj = (
        manifest.get("release")
        if isinstance(manifest.get("release"), Mapping)
        else {}
    )
    if expected_release:
        for key in ("product", "exact_head", "authority_sha256"):
            if (
                key in expected_release
                and release_obj.get(key) != expected_release.get(key)
            ):
                issues.append(
                    {"code": "RELEASE_BINDING_MISMATCH", "field": key}
                )

    result = {
        "phase": PHASE,
        "status": "PASS" if not issues else "FAIL",
        "verified": not issues,
        "issues": issues,
        "artifact_sha256": observed_artifact,
        "manifest_sha256": manifest.get("manifest_sha256"),
        "native_pass_inferred": False,
        "authority": "P416_OFFLINE_GENERATION_MANIFEST_VERIFIER",
    }
    result["verification_sha256"] = canonical_sha256(result)
    return result


def witness_ablation(manifest: Mapping[str, Any]) -> dict:
    witness = minimal_sufficient_generation_witness(manifest)
    rows = []
    for field in WITNESS_DEPENDENCIES:
        candidate = dict(witness)
        candidate.pop(field, None)
        missing = [
            x for x in WITNESS_DEPENDENCIES if x not in candidate
        ]
        rows.append(
            {
                "removed": field,
                "status": "FAIL" if missing else "PASS",
                "issues": [
                    {"code": "WITNESS_DEPENDENCY_MISSING", "field": x}
                    for x in missing
                ],
            }
        )
    result = {
        "phase": PHASE,
        "status": (
            "PASS" if all(x["status"] == "FAIL" for x in rows) else "FAIL"
        ),
        "dependency_count": len(WITNESS_DEPENDENCIES),
        "ablations": rows,
        "authority": "P416_EXPLICIT_WITNESS_DEPENDENCY_ABLATION",
    }
    result["ablation_sha256"] = canonical_sha256(result)
    return result


def classify_reproduction(
    reference_manifest: Mapping[str, Any],
    candidate_manifest: Mapping[str, Any],
    *,
    reference_structure_sha256: str | None = None,
    candidate_structure_sha256: str | None = None,
    reference_semantic_sha256: str | None = None,
    candidate_semantic_sha256: str | None = None,
) -> dict:
    ref_check = verify_generation_manifest(reference_manifest)
    cand_check = verify_generation_manifest(candidate_manifest)
    issues = []

    if not ref_check["verified"] or not cand_check["verified"]:
        verdict = "REPRODUCTION_FAILED"
        issues.append({"code": "INVALID_MANIFEST_INPUT"})
    elif (
        reference_manifest.get("artifact_sha256")
        == candidate_manifest.get("artifact_sha256")
    ):
        verdict = "BYTE_REPRODUCED"
    elif (
        reference_structure_sha256
        and candidate_structure_sha256
        and reference_structure_sha256 == candidate_structure_sha256
    ):
        verdict = "STRUCTURALLY_REPRODUCED"
    elif (
        reference_semantic_sha256
        and candidate_semantic_sha256
        and reference_semantic_sha256 == candidate_semantic_sha256
    ):
        verdict = "SEMANTICALLY_COMPATIBLE_BUT_NONIDENTICAL"
    else:
        verdict = "REPRODUCTION_FAILED"
        if (
            reference_manifest.get("intent_sha256")
            == candidate_manifest.get("intent_sha256")
            and reference_manifest.get("plan_sha256")
            == candidate_manifest.get("plan_sha256")
        ):
            issues.append({"code": "DETERMINISTIC_OUTPUT_DRIFT"})
        else:
            issues.append({"code": "REPRODUCTION_INPUT_OR_PLAN_DRIFT"})

    result = {
        "phase": PHASE,
        "verdict": verdict,
        "issues": issues,
        "reference_manifest_sha256": reference_manifest.get(
            "manifest_sha256"
        ),
        "candidate_manifest_sha256": candidate_manifest.get(
            "manifest_sha256"
        ),
        "structural_authority": (
            "P2_DOCUMENT_STRUCTURE_SHA256"
            if verdict == "STRUCTURALLY_REPRODUCED"
            else None
        ),
        "semantic_authority": (
            "P2_DOCUMENT_SEMANTIC_SHA256"
            if verdict == "SEMANTICALLY_COMPATIBLE_BUT_NONIDENTICAL"
            else None
        ),
        "native_equivalence_claimed": False,
        "authority": "P416_CROSS_RUN_REPRODUCTION_COURT",
    }
    result["reproduction_sha256"] = canonical_sha256(result)
    return result


def default_runtime_components(
    extra: Mapping[str, Any] | None = None,
) -> dict:
    base = {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "p416_product": PRODUCT,
    }
    if extra:
        base.update(normalize_structured_input(extra))
    return base


def _package_version(distribution: str) -> str:
    try:
        return importlib_metadata.version(distribution)
    except importlib_metadata.PackageNotFoundError:
        return "UNAVAILABLE"


def build_authoring_generation_manifest(
    path: str | Path,
    *,
    intent: Mapping[str, Any],
    plan: Mapping[str, Any],
    capability_path: Sequence[str],
    tool_trace: Sequence[Mapping[str, Any]],
    deterministic_parameters: Mapping[str, Any],
    source_inputs: Sequence[Mapping[str, Any]] = (),
    parent_document: Mapping[str, Any] | None = None,
    native_evidence_refs: Sequence[Mapping[str, Any]] = (),
) -> dict:
    return compile_generation_manifest_for_file(
        path,
        intent=intent,
        plan=plan,
        capability_path=capability_path,
        tool_trace=tool_trace,
        source_inputs=source_inputs,
        runtime_components=default_runtime_components(
            {
                "python-hwpx": _package_version("python-hwpx"),
                "mcp": _package_version("mcp"),
            }
        ),
        deterministic_parameters=deterministic_parameters,
        parent_document=parent_document,
        native_evidence_refs=native_evidence_refs,
    )
