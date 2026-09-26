from __future__ import annotations

import copy
import threading
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from mcp.types import ToolAnnotations

from p347_supply_chain_bridge import (
    compare_host_conformance,
    compare_reproducible_builds,
    certify_extension_package,
    normalize_extension_package,
    solve_package_compatibility,
    supply_chain_contract,
    validate_rollout_transition,
    validate_certified_rollback,
    verify_certificate,
    verify_dependency_closure,
)


@dataclass(frozen=True)
class CertifiedPackage:
    package_id: str
    extension_id: str
    version: str
    package: Mapping[str, Any]
    normalized: Mapping[str, Any]
    certificate: Mapping[str, Any]


class CertifiedPackageRegistry:
    """Immutable package catalog with owner-scoped rollout state and generation CAS."""

    def __init__(self):
        self._lock = threading.RLock()
        self._catalog: dict[str, CertifiedPackage] = {}
        self._document_generation: dict[str, int] = {}
        self._document_states: dict[str, dict[str, str]] = {}
        self._document_promoted: dict[str, dict[str, str]] = {}
        self._document_history: dict[str, list[dict]] = {}

    def _state(self, document_id: str) -> tuple[int, dict[str, str], dict[str, str], list[dict]]:
        document_id = str(document_id or "")
        if not document_id:
            raise ValueError("P3.47 rollout registry requires document_id")
        if document_id not in self._document_generation:
            self._document_generation[document_id] = 1
            self._document_states[document_id] = {}
            self._document_promoted[document_id] = {}
            self._document_history[document_id] = []
        return (
            self._document_generation[document_id],
            self._document_states[document_id],
            self._document_promoted[document_id],
            self._document_history[document_id],
        )

    @staticmethod
    def _catalog_fingerprint(item: CertifiedPackage) -> tuple:
        return (
            item.package_id,
            item.extension_id,
            item.version,
            item.normalized.get("artifact_sha256"),
            item.certificate.get("certificate_sha256"),
        )

    def snapshot(self, document_id: str) -> dict:
        with self._lock:
            generation, states, promoted, history = self._state(document_id)
            rows = []
            for package_id, state in sorted(states.items()):
                item = self._catalog[package_id]
                rows.append(
                    {
                        "package_id": package_id,
                        "extension_id": item.extension_id,
                        "version": item.version,
                        "state": state,
                        "artifact_sha256": item.normalized.get("artifact_sha256"),
                        "certificate_sha256": item.certificate.get("certificate_sha256"),
                    }
                )
            return {
                "phase": "P3.47",
                "document_id": document_id,
                "generation": generation,
                "packages": rows,
                "promoted_by_extension": dict(sorted(promoted.items())),
                "history": copy.deepcopy(history[-32:]),
                "scope": "OWNER_SCOPED_DOCUMENT_ROLLOUT",
                "catalog_visibility": "ONLY_PACKAGES_ADMITTED_TO_THIS_DOCUMENT",
            }

    def install(
        self,
        package: Mapping[str, Any],
        certificate: Mapping[str, Any],
        *,
        document_id: str,
        expected_generation: int,
    ) -> dict:
        normalized = normalize_extension_package(package)
        verified = verify_certificate(certificate)
        package_id = str(normalized["package_id"])
        if str(certificate.get("package_id") or "") != package_id:
            raise RuntimeError("P3.47 certificate/package identity mismatch")
        if not verified["typescript"].get("ok") or not verified["rust"].get("ok"):
            raise RuntimeError("P3.47 certificate verification did not pass both runtimes")

        with self._lock:
            generation, states, _promoted, history = self._state(document_id)
            if int(expected_generation) != generation:
                raise RuntimeError("P3.47 package registry generation CAS mismatch")
            item = CertifiedPackage(
                package_id=package_id,
                extension_id=str(normalized["extension"]["extension_id"]),
                version=str(normalized["extension"]["version"]),
                package=copy.deepcopy(dict(package)),
                normalized=copy.deepcopy(normalized),
                certificate=copy.deepcopy(dict(certificate)),
            )
            prior = self._catalog.get(package_id)
            if prior is not None and self._catalog_fingerprint(prior) != self._catalog_fingerprint(item):
                raise RuntimeError("P3.47 content-addressed package catalog collision")
            self._catalog[package_id] = item

            if package_id in states:
                raise RuntimeError("P3.47 package already admitted to document")
            states[package_id] = "INSTALLED"
            self._document_generation[document_id] = generation + 1
            history.append(
                {
                    "action": "INSTALL",
                    "package_id": package_id,
                    "extension_id": item.extension_id,
                    "from": None,
                    "to": "INSTALLED",
                    "generation_before": generation,
                    "generation_after": generation + 1,
                }
            )
            out = self.snapshot(document_id)
            out.update(
                {
                    "installed_package_id": package_id,
                    "authority": "CERTIFIED_CONTENT_ADDRESSED_PACKAGE_INSTALL_PASS",
                }
            )
            return out

    def advance(
        self,
        package_id: str,
        target_state: str,
        *,
        document_id: str,
        expected_generation: int,
    ) -> dict:
        package_id = str(package_id or "")
        with self._lock:
            generation, states, promoted, history = self._state(document_id)
            if int(expected_generation) != generation:
                raise RuntimeError("P3.47 package registry generation CAS mismatch")
            if package_id not in states or package_id not in self._catalog:
                raise KeyError("P3.47 package is not admitted to document")
            current = states[package_id]
            item = self._catalog[package_id]
            transition = validate_rollout_transition(current, target_state, item.certificate)

            dependency_states = {
                str(dep.get("package_id")): states.get(str(dep.get("package_id")))
                for dep in item.normalized.get("dependencies") or []
            }
            if target_state in {"SHADOW", "CANARY", "PROMOTED"}:
                allowed_by_target = {
                    "SHADOW": {"SHADOW", "CANARY", "PROMOTED"},
                    "CANARY": {"CANARY", "PROMOTED"},
                    "PROMOTED": {"PROMOTED"},
                }[target_state]
                bad = {
                    dep: state for dep, state in dependency_states.items()
                    if state not in allowed_by_target
                }
                if bad:
                    raise RuntimeError(
                        f"P3.47 dependency rollout state not admissible for {target_state}: {bad}"
                    )

            replaced_package_id = None
            if target_state == "PROMOTED":
                previous = promoted.get(item.extension_id)
                if previous and previous != package_id:
                    if states.get(previous) != "PROMOTED":
                        raise RuntimeError("P3.47 promoted pointer/state divergence")
                    previous_item = self._catalog[previous]
                    validate_rollout_transition("PROMOTED", "RETIRED", previous_item.certificate)
                    states[previous] = "RETIRED"
                    replaced_package_id = previous
                promoted[item.extension_id] = package_id

            if target_state == "RETIRED" and promoted.get(item.extension_id) == package_id:
                promoted.pop(item.extension_id, None)

            states[package_id] = target_state
            self._document_generation[document_id] = generation + 1
            history.append(
                {
                    "action": "ADVANCE",
                    "package_id": package_id,
                    "extension_id": item.extension_id,
                    "from": current,
                    "to": target_state,
                    "replaced_package_id": replaced_package_id,
                    "generation_before": generation,
                    "generation_after": generation + 1,
                }
            )
            out = self.snapshot(document_id)
            out.update(
                {
                    "package_id": package_id,
                    "from_state": current,
                    "to_state": target_state,
                    "replaced_package_id": replaced_package_id,
                    "dependency_states": dependency_states,
                    "typescript_transition": transition["typescript"],
                    "rust_transition": transition["rust"],
                    "authority": "CERTIFIED_PACKAGE_ROLLOUT_TRANSITION_PASS",
                }
            )
            return out

    def rollback(
        self,
        extension_id: str,
        *,
        document_id: str,
        expected_generation: int,
    ) -> dict:
        extension_id = str(extension_id or "")
        with self._lock:
            generation, states, promoted, history = self._state(document_id)
            if int(expected_generation) != generation:
                raise RuntimeError("P3.47 package registry generation CAS mismatch")
            current_id = promoted.get(extension_id)
            if not current_id:
                raise RuntimeError("P3.47 extension has no promoted package")

            candidates: list[str] = []
            for row in reversed(history):
                if row.get("extension_id") != extension_id:
                    continue
                candidate = row.get("replaced_package_id")
                if candidate and candidate != current_id and candidate in states:
                    candidates.append(str(candidate))
            if not candidates:
                raise RuntimeError("P3.47 rollback history has no prior promoted package")
            previous_id = candidates[0]
            current_item = self._catalog[current_id]
            previous_item = self._catalog[previous_id]
            verify_certificate(current_item.certificate)
            verify_certificate(previous_item.certificate)
            if states.get(current_id) != "PROMOTED":
                raise RuntimeError("P3.47 current promoted package state divergence")
            if states.get(previous_id) != "RETIRED":
                raise RuntimeError("P3.47 rollback target is not retired prior promotion")

            validate_rollout_transition("PROMOTED", "RETIRED", current_item.certificate)
            rollback_guard = validate_certified_rollback(
                current_item.certificate,
                previous_item.certificate,
            )
            states[current_id] = "RETIRED"
            states[previous_id] = "PROMOTED"
            promoted[extension_id] = previous_id
            self._document_generation[document_id] = generation + 1
            history.append(
                {
                    "action": "ROLLBACK",
                    "extension_id": extension_id,
                    "from_package_id": current_id,
                    "to_package_id": previous_id,
                    "generation_before": generation,
                    "generation_after": generation + 1,
                }
            )
            out = self.snapshot(document_id)
            out.update(
                {
                    "extension_id": extension_id,
                    "retired_package_id": current_id,
                    "restored_package_id": previous_id,
                    "rollback_guard": rollback_guard,
                    "authority": "ATOMIC_CERTIFIED_PACKAGE_ROLLBACK_PASS",
                }
            )
            return out


def register_p347_tools(
    core,
    owned_document: Callable[[str], tuple[dict, Any]],
    registry: CertifiedPackageRegistry,
):
    read_only = ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        openWorldHint=False,
    )
    runtime_config = ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        openWorldHint=False,
    )

    def _own(document_id: str) -> None:
        owned_document(document_id)

    @core.mcp.tool(annotations=read_only)
    def get_extension_supply_chain_contract() -> dict:
        core._caller_subject()
        return {"ok": True, **supply_chain_contract()}

    @core.mcp.tool(annotations=read_only)
    def verify_extension_package(
        package: dict,
        dependency_catalog: list[dict] | None = None,
    ) -> dict:
        core._caller_subject()
        normalized = normalize_extension_package(package)
        closure = verify_dependency_closure(package, dependency_catalog or [])
        return {"ok": True, "package": normalized, "dependency_closure": closure}

    @core.mcp.tool(annotations=read_only)
    def compare_extension_build_reproducibility(left: dict, right: dict) -> dict:
        core._caller_subject()
        result = compare_reproducible_builds(left, right)
        return {"ok": bool(result["reproducible"]), **result}

    @core.mcp.tool(annotations=read_only)
    def solve_extension_package_compatibility(current: dict, candidate: dict) -> dict:
        core._caller_subject()
        result = solve_package_compatibility(current, candidate)
        return {"ok": True, **result}

    @core.mcp.tool(annotations=read_only)
    def compare_extension_host_conformance(observations: list[dict]) -> dict:
        core._caller_subject()
        result = compare_host_conformance(observations)
        return {"ok": result["verdict"] == "PASS", **result}

    @core.mcp.tool(annotations=read_only)
    def certify_document_extension_package(
        package: dict,
        rebuild_package: dict,
        host_observations: list[dict],
        dependency_catalog: list[dict] | None = None,
    ) -> dict:
        core._caller_subject()
        result = certify_extension_package(
            package,
            rebuild_package=rebuild_package,
            catalog=dependency_catalog or [],
            host_observations=host_observations,
        )
        return {
            "ok": result["certificate"]["status"] == "PASS"
            and bool(result["rust"].get("ok")),
            **result,
        }

    @core.mcp.tool(annotations=read_only)
    def get_certified_extension_registry(document_id: str) -> dict:
        _own(document_id)
        return {"ok": True, **registry.snapshot(document_id)}

    @core.mcp.tool(annotations=runtime_config)
    def install_certified_extension_package(
        document_id: str,
        package: dict,
        certificate: dict,
        expected_generation: int,
    ) -> dict:
        _own(document_id)
        return {
            "ok": True,
            **registry.install(
                package,
                certificate,
                document_id=document_id,
                expected_generation=int(expected_generation),
            ),
        }

    @core.mcp.tool(annotations=runtime_config)
    def advance_extension_package_rollout(
        document_id: str,
        package_id: str,
        target_state: str,
        expected_generation: int,
    ) -> dict:
        _own(document_id)
        return {
            "ok": True,
            **registry.advance(
                package_id,
                target_state,
                document_id=document_id,
                expected_generation=int(expected_generation),
            ),
        }

    @core.mcp.tool(annotations=runtime_config)
    def rollback_extension_package_rollout(
        document_id: str,
        extension_id: str,
        expected_generation: int,
    ) -> dict:
        _own(document_id)
        return {
            "ok": True,
            **registry.rollback(
                extension_id,
                document_id=document_id,
                expected_generation=int(expected_generation),
            ),
        }

    return registry
