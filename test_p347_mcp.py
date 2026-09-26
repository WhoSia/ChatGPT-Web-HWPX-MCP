from __future__ import annotations

import pytest

import p347_mcp
from p347_mcp import CertifiedPackageRegistry, register_p347_tools


class _MCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *, annotations=None):
        def decorate(fn):
            self.tools[fn.__name__] = fn
            return fn
        return decorate


class _Core:
    def __init__(self):
        self.mcp = _MCP()

    @staticmethod
    def _caller_subject():
        return "pytest"


def _normalized(package_id: str, extension_id: str = "ext", version: str = "1.0.0") -> dict:
    return {
        "package_id": package_id,
        "artifact_sha256": "a" * 64,
        "extension": {"extension_id": extension_id, "version": version},
    }


def _certificate(package_id: str, seal: str = "b" * 64) -> dict:
    return {
        "schema": "chatgpt-web-hwpx-mcp/p3.47/certification-certificate/v1",
        "package_id": package_id,
        "certificate_sha256": seal,
        "status": "PASS",
    }


def test_owner_scoped_certified_registry_rollout_replacement_and_rollback(monkeypatch):
    pkg1 = "sha256:" + "1" * 64
    pkg2 = "sha256:" + "2" * 64

    monkeypatch.setattr(
        p347_mcp,
        "normalize_extension_package",
        lambda package: _normalized(
            package["package_id"],
            package.get("extension_id", "ext"),
            package.get("version", "1.0.0"),
        ),
    )
    monkeypatch.setattr(
        p347_mcp,
        "verify_certificate",
        lambda cert: {"typescript": {"ok": True}, "rust": {"ok": True}},
    )
    monkeypatch.setattr(
        p347_mcp,
        "validate_rollout_transition",
        lambda f, t, cert: {
            "typescript": {"from": f, "to": t, "authority": "ROLLOUT_TRANSITION_GOVERNANCE_PASS"},
            "rust": {"from": f, "to": t, "authority": "RUST_ROLLOUT_TRANSITION_PASS"},
        },
    )
    monkeypatch.setattr(
        p347_mcp,
        "validate_certified_rollback",
        lambda current, target: {
            "typescript": {
                "current_package_id": current["package_id"],
                "target_package_id": target["package_id"],
            },
            "rust": {
                "current_package_id": current["package_id"],
                "target_package_id": target["package_id"],
            },
            "authority": "CROSS_RUNTIME_CERTIFIED_ROLLBACK_PASS",
        },
    )

    registry = CertifiedPackageRegistry()
    a = registry.install({"package_id": pkg1}, _certificate(pkg1), document_id="doc-a", expected_generation=1)
    assert a["generation"] == 2
    assert registry.snapshot("doc-b")["packages"] == []

    for state in ["CANDIDATE", "SHADOW", "CANARY", "PROMOTED"]:
        snap = registry.snapshot("doc-a")
        registry.advance(pkg1, state, document_id="doc-a", expected_generation=snap["generation"])
    assert registry.snapshot("doc-a")["promoted_by_extension"]["ext"] == pkg1

    snap = registry.snapshot("doc-a")
    registry.install(
        {"package_id": pkg2, "version": "1.1.0"},
        _certificate(pkg2, "c" * 64),
        document_id="doc-a",
        expected_generation=snap["generation"],
    )
    for state in ["CANDIDATE", "SHADOW", "CANARY", "PROMOTED"]:
        snap = registry.snapshot("doc-a")
        registry.advance(pkg2, state, document_id="doc-a", expected_generation=snap["generation"])
    after = registry.snapshot("doc-a")
    states = {row["package_id"]: row["state"] for row in after["packages"]}
    assert states[pkg1] == "RETIRED"
    assert states[pkg2] == "PROMOTED"

    rolled = registry.rollback("ext", document_id="doc-a", expected_generation=after["generation"])
    assert rolled["restored_package_id"] == pkg1
    assert rolled["promoted_by_extension"]["ext"] == pkg1
    assert rolled["rollback_guard"]["authority"] == "CROSS_RUNTIME_CERTIFIED_ROLLBACK_PASS"


def test_registry_generation_cas(monkeypatch):
    package_id = "sha256:" + "3" * 64
    monkeypatch.setattr(
        p347_mcp,
        "normalize_extension_package",
        lambda package: _normalized(package_id),
    )
    monkeypatch.setattr(
        p347_mcp,
        "verify_certificate",
        lambda cert: {"typescript": {"ok": True}, "rust": {"ok": True}},
    )

    registry = CertifiedPackageRegistry()
    registry.install({}, _certificate(package_id), document_id="doc", expected_generation=1)
    with pytest.raises(RuntimeError, match="generation CAS"):
        registry.advance(
            package_id,
            "CANDIDATE",
            document_id="doc",
            expected_generation=1,
        )


def test_mcp_registration_requires_ownership_for_registry(monkeypatch):
    core = _Core()
    owned = {"doc": ({"revision": 1}, object())}

    monkeypatch.setattr(p347_mcp, "supply_chain_contract", lambda: {"phase": "P3.47"})
    registry = CertifiedPackageRegistry()
    register_p347_tools(core, lambda document_id: owned[document_id], registry)
    names = set(core.mcp.tools)
    assert {
        "get_extension_supply_chain_contract",
        "verify_extension_package",
        "compare_extension_build_reproducibility",
        "solve_extension_package_compatibility",
        "compare_extension_host_conformance",
        "certify_document_extension_package",
        "get_certified_extension_registry",
        "install_certified_extension_package",
        "advance_extension_package_rollout",
        "rollback_extension_package_rollout",
    } <= names
    assert core.mcp.tools["get_extension_supply_chain_contract"]()["phase"] == "P3.47"
    with pytest.raises(KeyError):
        core.mcp.tools["get_certified_extension_registry"]("not-owned")
