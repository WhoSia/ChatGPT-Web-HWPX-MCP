from __future__ import annotations

from typing import Any, Callable, Mapping

from p343_design_system import (
    build_cross_template_generalization_ledger,
    design_system_adaptation_contract,
    normalize_organization_policy,
    plan_constraint_preserving_style_transfer,
)


def register_p343_tools(core, owned_document, corpus_registry, apply_migration: Callable[..., dict]):
    def owner() -> str:
        return core._caller_subject()

    def current_template_evidence(template: Mapping[str, Any]) -> dict:
        current = {
            str(row.get("source_id")): str(row.get("source_receipt_sha256") or "")
            for row in corpus_registry.records(owner())
        }
        receipts = template.get("source_receipts") or {}
        if not isinstance(receipts, Mapping) or not receipts:
            raise ValueError("TEMPLATE_SOURCE_RECEIPTS_REQUIRED")
        stale = [str(source_id) for source_id, expected in receipts.items() if current.get(str(source_id)) != str(expected)]
        if stale:
            raise ValueError("STALE_TEMPLATE_EVIDENCE:" + ",".join(sorted(stale)))
        return {"source_count": len(receipts), "source_receipts_current": True}

    @core.mcp.tool()
    def get_organization_template_adaptation_contract() -> dict:
        """Return P3.43 hard/soft organization policy and evidence-carrying migration semantics."""
        owner()
        return {"ok": True, **design_system_adaptation_contract()}

    @core.mcp.tool()
    def validate_organization_design_policy(policy: dict) -> dict:
        """Normalize and hash one explicit organization/brand design policy without mutation."""
        owner()
        return {"ok": True, "policy": normalize_organization_policy(policy)}

    @core.mcp.tool()
    def plan_organization_template_migration(document_id: str, template: dict, targets_by_role: dict, policy: dict, expected_revision: int) -> dict:
        """Compile one evidence-current template candidate under hard organization constraints."""
        metadata, path = owned_document(document_id)
        current = int(metadata["revision"])
        if int(expected_revision) != current:
            raise ValueError(f"Stale revision: expected {expected_revision}, current {current}")
        evidence = current_template_evidence(template)
        plan = plan_constraint_preserving_style_transfer(path, template, targets_by_role, policy, expected_revision=current)
        return {"ok": True, "document_id": document_id, "revision": current, "evidence_freshness": evidence, **plan}

    @core.mcp.tool()
    def apply_organization_template_migration(document_id: str, template: dict, targets_by_role: dict, policy: dict, expected_revision: int, lease_token: str = "") -> dict:
        """Apply hard-policy-constrained style migration with P3.42 footprint enforcement before commit."""
        current_template_evidence(template)
        return apply_migration(
            document_id=document_id, template=template, targets_by_role=targets_by_role,
            policy=policy, expected_revision=int(expected_revision), lease_token=str(lease_token or ""),
        )

    @core.mcp.tool()
    def adjudicate_cross_template_generalization(cases: list[dict], min_holdout_templates: int = 2, min_holdout_institutions: int = 2) -> dict:
        """Adjudicate a denominator-preserving DISCOVERY/HOLDOUT migration matrix."""
        owner()
        return {"ok": True, **build_cross_template_generalization_ledger(
            cases, min_holdout_templates=int(min_holdout_templates),
            min_holdout_institutions=int(min_holdout_institutions),
        )}

    return {"phase": "P3.43", "contract": design_system_adaptation_contract()}
