from __future__ import annotations

import copy

from p416_generation_manifest import (
    PARENT_RELEASE_AUTHORITY_SHA256,
    canonical_sha256,
    classify_reproduction,
    compile_generation_manifest,
    minimal_sufficient_generation_witness,
    verify_generation_manifest,
    witness_ablation,
)


HEAD = "1" * 40
ARTIFACT = "a" * 64
RELEASE = {
    "product": "0.41.0-p4.16",
    "exact_head": HEAD,
    "authority_sha256": PARENT_RELEASE_AUTHORITY_SHA256,
    "authority_scope": "TEST",
}


def make_manifest(**overrides):
    args = {
        "intent": {
            "document": {
                "title": "Alpha",
                "blocks": [{"kind": "paragraph", "text": "x"}],
            }
        },
        "plan": {"lane": "unified", "ops": [{"kind": "compose", "id": 1}]},
        "capability_path": ["AUTHORING", "COMPOSE", "DELIVER"],
        "tool_trace": [
            {
                "tool": "compose_document_plan",
                "capability": "COMPOSE",
                "operation": {"plan": "p"},
            },
            {
                "tool": "validate_hwpx_package",
                "capability": "VALIDATE",
                "operation": {},
            },
        ],
        "source_inputs": [
            {
                "source_id": "request",
                "kind": "structured_spec",
                "value": {"x": 1, "y": 2},
            }
        ],
        "runtime_components": {
            "python": "3.12.13",
            "python-hwpx": "6.6.0",
        },
        "deterministic_parameters": {
            "filename": "document.hwpx",
            "mode": "POLISHED_REPORT",
        },
        "artifact_sha256": ARTIFACT,
        "release": RELEASE,
    }
    args.update(overrides)
    return compile_generation_manifest(**args)


def test_mapping_key_order_normalizes_but_sequence_order_does_not():
    a = make_manifest(intent={"b": 2, "a": {"y": 2, "x": 1}})
    b = make_manifest(intent={"a": {"x": 1, "y": 2}, "b": 2})
    assert a["intent_sha256"] == b["intent_sha256"]

    c = make_manifest(plan={"ops": [1, 2]})
    d = make_manifest(plan={"ops": [2, 1]})
    assert c["plan_sha256"] != d["plan_sha256"]


def test_metadata_label_whitespace_is_normalized_only_on_declared_labels():
    a = make_manifest(capability_path=[" AUTHORING  ", "COMPOSE"])
    b = make_manifest(capability_path=["AUTHORING", "COMPOSE"])
    assert a["capability_path_sha256"] == b["capability_path_sha256"]

    c = make_manifest(intent={"text": "a  b"})
    d = make_manifest(intent={"text": "a b"})
    assert c["intent_sha256"] != d["intent_sha256"]


def test_manifest_roundtrip_and_artifact_binding_pass():
    manifest = make_manifest()
    result = verify_generation_manifest(
        manifest,
        artifact_sha256=ARTIFACT,
    )
    assert result["status"] == "PASS"
    assert result["native_pass_inferred"] is False


def test_manifest_document_swap_is_fatal():
    result = verify_generation_manifest(
        make_manifest(),
        artifact_sha256="b" * 64,
    )
    assert result["status"] == "FAIL"
    assert any(
        x["code"] == "ARTIFACT_MANIFEST_BINDING_MISMATCH"
        for x in result["issues"]
    )


def test_tool_trace_tamper_is_fatal_even_if_outer_digest_resealed():
    manifest = make_manifest()
    manifest["tool_trace"][0]["tool"] = "forged_tool"
    manifest["manifest_sha256"] = canonical_sha256(
        {
            k: v
            for k, v in manifest.items()
            if k != "manifest_sha256"
        }
    )
    result = verify_generation_manifest(manifest)
    assert any(
        x["code"] == "TOOL_TRACE_DIGEST_MISMATCH"
        for x in result["issues"]
    )


def test_hidden_parameter_drift_changes_manifest():
    a = make_manifest(
        deterministic_parameters={"mode": "A", "seed": 1}
    )
    b = make_manifest(
        deterministic_parameters={"mode": "A", "seed": 2}
    )
    assert (
        a["deterministic_parameters_sha256"]
        != b["deterministic_parameters_sha256"]
    )
    assert a["manifest_sha256"] != b["manifest_sha256"]


def test_wrong_release_head_is_detected():
    manifest = make_manifest()
    result = verify_generation_manifest(
        manifest,
        expected_release={"exact_head": "2" * 40},
    )
    assert any(
        x["code"] == "RELEASE_BINDING_MISMATCH"
        for x in result["issues"]
    )


def test_stale_runtime_version_changes_manifest():
    a = make_manifest(
        runtime_components={
            "python": "3.12.13",
            "python-hwpx": "6.6.0",
        }
    )
    b = make_manifest(
        runtime_components={
            "python": "3.12.13",
            "python-hwpx": "6.7.0",
        }
    )
    assert (
        a["runtime_components_sha256"]
        != b["runtime_components_sha256"]
    )


def test_minimal_witness_ablation_proves_each_dependency_required():
    manifest = make_manifest()
    witness = minimal_sufficient_generation_witness(manifest)
    assert witness["witness_sha256"]

    ablation = witness_ablation(manifest)
    assert ablation["status"] == "PASS"
    assert all(
        row["status"] == "FAIL"
        for row in ablation["ablations"]
    )


def test_missing_witness_field_fails_manifest_verification():
    manifest = make_manifest()
    manifest["minimal_witness"].pop("plan_sha256")
    manifest["manifest_sha256"] = canonical_sha256(
        {
            k: v
            for k, v in manifest.items()
            if k != "manifest_sha256"
        }
    )
    result = verify_generation_manifest(manifest)
    assert any(
        x["code"] == "MINIMAL_WITNESS_MISMATCH"
        for x in result["issues"]
    )


def test_reproduction_court_uses_existing_structural_and_semantic_authorities_only():
    a = make_manifest()
    b = copy.deepcopy(a)
    assert classify_reproduction(a, b)["verdict"] == "BYTE_REPRODUCED"

    b = make_manifest(artifact_sha256="b" * 64)
    structural = classify_reproduction(
        a,
        b,
        reference_structure_sha256="c" * 64,
        candidate_structure_sha256="c" * 64,
    )
    assert structural["verdict"] == "STRUCTURALLY_REPRODUCED"

    semantic = classify_reproduction(
        a,
        b,
        reference_semantic_sha256="d" * 64,
        candidate_semantic_sha256="d" * 64,
    )
    assert (
        semantic["verdict"]
        == "SEMANTICALLY_COMPATIBLE_BUT_NONIDENTICAL"
    )
    assert semantic["native_equivalence_claimed"] is False


def test_deterministic_replay_drift_is_not_downgraded_to_semantic_claim():
    a = make_manifest()
    b = make_manifest(artifact_sha256="b" * 64)
    result = classify_reproduction(a, b)
    assert result["verdict"] == "REPRODUCTION_FAILED"
    assert any(
        x["code"] == "DETERMINISTIC_OUTPUT_DRIFT"
        for x in result["issues"]
    )
