from __future__ import annotations

import pytest

from p346_mcp import AdapterRegistry


def _readonly(**kwargs):
    return {
        "revision_after": int(kwargs["current_revision"]),
        "output_sha256": "a" * 64,
    }


def _mutation(**kwargs):
    return {
        "revision_after": int(kwargs["current_revision"]) + 1,
        "output_sha256": "b" * 64,
    }


def test_hot_swap_registry_cas_guard_and_rollback():
    registry = AdapterRegistry({
        "DOCUMENT_SNAPSHOT": _readonly,
        "DOCUMENT_TEXT_EDIT": _mutation,
    })
    snap = registry.snapshot("doc-a")
    assert snap["active_profile"] == "p3.46-guarded"
    assert registry.resolve("DOCUMENT_SNAPSHOT", document_id="doc-a")(
        document_id="doc-a",
        current_revision=3,
        inputs={},
        lease_token="",
    )["revision_after"] == 3
    mutation = registry.resolve("DOCUMENT_TEXT_EDIT", document_id="doc-a")(
        document_id="doc-a",
        current_revision=3,
        inputs={},
        lease_token="",
    )
    assert mutation["revision_after"] == 4
    assert mutation["p346_adapter_profile"] == "p3.46-guarded"

    swapped = registry.swap(
        "p3.45-compat",
        snap["generation"],
        document_id="doc-a",
    )
    assert swapped["swapped"] is True
    assert swapped["active_profile"] == "p3.45-compat"
    assert registry.snapshot("doc-b")["active_profile"] == "p3.46-guarded"
    assert registry.snapshot("doc-b")["generation"] == 1
    with pytest.raises(RuntimeError, match="generation CAS"):
        registry.swap(
            "p3.46-guarded",
            snap["generation"],
            document_id="doc-a",
        )

    rolled = registry.rollback(
        swapped["generation"],
        document_id="doc-a",
    )
    assert rolled["rolled_back_to"] == "p3.46-guarded"
    assert rolled["active_profile"] == "p3.46-guarded"


def test_guard_rejects_revision_contract_violation():
    def bad(**kwargs):
        return {"revision_after": int(kwargs["current_revision"]) + 2}

    registry = AdapterRegistry({"DOCUMENT_TEXT_EDIT": bad})
    with pytest.raises(RuntimeError, match="revision contract failed"):
        registry.resolve("DOCUMENT_TEXT_EDIT", document_id="doc-a")(
            document_id="d",
            current_revision=7,
            inputs={},
            lease_token="",
        )


def test_arbitrary_profile_registration_is_not_exposed():
    registry = AdapterRegistry({"DOCUMENT_SNAPSHOT": _readonly})
    with pytest.raises(ValueError, match="not pre-admitted"):
        registry.swap(
            "uploaded-python-code",
            registry.snapshot("doc-a")["generation"],
            document_id="doc-a",
        )


def test_run_local_binding_survives_document_swap_and_restart_hint():
    registry = AdapterRegistry({
        "DOCUMENT_SNAPSHOT": _readonly,
    })
    first = registry.resolve(
        "DOCUMENT_SNAPSHOT",
        document_id="doc-a",
        run_id="run-1",
    )
    first_receipt = first(
        document_id="doc-a",
        current_revision=3,
        inputs={},
        lease_token="",
    )
    assert first_receipt["p346_adapter_profile"] == "p3.46-guarded"
    assert first_receipt["p346_adapter_generation"] == 1

    snap = registry.snapshot("doc-a")
    registry.swap(
        "p3.45-compat",
        snap["generation"],
        document_id="doc-a",
    )

    same_run = registry.resolve(
        "DOCUMENT_SNAPSHOT",
        document_id="doc-a",
        run_id="run-1",
    )
    same_receipt = same_run(
        document_id="doc-a",
        current_revision=3,
        inputs={},
        lease_token="",
    )
    assert same_receipt["p346_adapter_profile"] == "p3.46-guarded"
    assert same_receipt["p346_adapter_generation"] == 1

    next_run = registry.resolve(
        "DOCUMENT_SNAPSHOT",
        document_id="doc-a",
        run_id="run-2",
    )
    next_receipt = next_run(
        document_id="doc-a",
        current_revision=3,
        inputs={},
        lease_token="",
    )
    assert next_receipt["p346_adapter_profile"] == "p3.45-compat"
    assert next_receipt["p346_adapter_generation"] == 2

    restarted = AdapterRegistry({"DOCUMENT_SNAPSHOT": _readonly})
    recovered = restarted.resolve(
        "DOCUMENT_SNAPSHOT",
        document_id="doc-a",
        run_id="run-2",
        pinned_profile="p3.45-compat",
        pinned_generation=2,
    )
    recovered_receipt = recovered(
        document_id="doc-a",
        current_revision=3,
        inputs={},
        lease_token="",
    )
    assert recovered_receipt["p346_adapter_profile"] == "p3.45-compat"
    assert recovered_receipt["p346_adapter_generation"] == 2
