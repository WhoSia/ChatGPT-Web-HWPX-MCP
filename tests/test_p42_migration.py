from __future__ import annotations

import pytest

from p42_migration import adjudicate_upgrade, migration_contract, normalize_list_number_format, semantic_page_geometry

def test_page_geometry_normalizes_66_and_legacy_65_to_same_semantics():
    modern=semantic_page_geometry(59528,84189,"NARROWLY")
    legacy=semantic_page_geometry(84189,59528,"WIDELY")
    assert modern["orientation"]==legacy["orientation"]=="LANDSCAPE"
    assert modern["width"]==legacy["width"]==84189
    assert modern["height"]==legacy["height"]==59528
    assert modern["storage_orientation"]=="NARROWLY"
    assert legacy["orientation_authority"]=="LEGACY_6_5_GEOMETRY_OVERRIDE"

def test_portrait_storage_remains_portrait():
    modern=semantic_page_geometry(59528,84189,"WIDELY")
    assert modern["orientation"]=="PORTRAIT"
    assert modern["width"]<modern["height"]

def test_list_format_migrates_legacy_default_pattern_without_guessing():
    normalized,receipt=normalize_list_number_format("^1.",level=1)
    assert normalized=="DIGIT"
    assert receipt["status"]=="MIGRATED"
    normalized2,canonical=normalize_list_number_format("number",level=1)
    assert normalized2=="DIGIT"
    assert canonical["status"]=="CANONICAL"
    with pytest.raises(ValueError):
        normalize_list_number_format("^1.^2.",level=1)

def test_upgrade_adjudication_requires_every_product_gate():
    evidence={
        "candidate_targeted_regressions":True,
        "real_document_matrix":True,
        "performance_budget":True,
        "candidate_docker":True,
        "rollback_rehearsal":True,
    }
    assert adjudicate_upgrade(evidence)["verdict"]=="READY_FOR_PROMOTION_COMMIT"
    assert adjudicate_upgrade({**evidence,"real_document_matrix":False})["verdict"]=="HOLD"
    contract=migration_contract()
    assert contract["promotion_policy"]=="EVIDENCE_GATED_NO_AUTOMATIC_DEPENDENCY_PROMOTION"
