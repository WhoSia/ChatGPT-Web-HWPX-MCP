from __future__ import annotations

from p49_equation_witnesses import alignment_witness_contract, adjudicate_alignment_witness


def test_alignment_witness_is_same_cargo_left_center_right_triad():
    contract = alignment_witness_contract()
    assert contract["witness_kind"] == "SAME_CARGO_ALIGNMENT_TRIAD"
    assert [row["variant_id"] for row in contract["variants"]] == ["lpile", "pile", "rpile"]
    assert [row["expected_alignment"] for row in contract["variants"]] == ["LEFT", "CENTER", "RIGHT"]
    assert len({row["cargo"] for row in contract["variants"]}) == 1
    assert contract["p47_frontier_unchanged"] is True


def test_alignment_witness_does_not_promote_without_native_receipt():
    result = adjudicate_alignment_witness(None)
    assert result["status"] == "WORLD_CONTACT_PENDING"
    assert result["eligible"] == []
    assert set(result["held"]) == {"lpile", "pile"}
