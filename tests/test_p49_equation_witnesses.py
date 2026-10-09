from __future__ import annotations

import json
import tempfile
from pathlib import Path
from hwpx_mcp.quality.p49_equation_witnesses import alignment_witness_contract, adjudicate_alignment_witness
from scripts.p49_materialize_equation_witnesses import run as materialize_alignment_witnesses


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


def test_materialized_alignment_packet_contains_pending_adjudication_template():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        result = materialize_alignment_witnesses(out)
        template_path = out / result["adjudication_template"]
        assert template_path.exists()
        template = json.loads(template_path.read_text(encoding="utf-8"))
        assert [row["expected_alignment"] for row in template["variants"]] == ["LEFT", "CENTER", "RIGHT"]
        assert all(row["human_visual_status"] == "PENDING" for row in template["variants"])
        assert all(row["pdf_sha256"] is None for row in template["variants"])
        assert all(len(row["source_hwpx_sha256"]) == 64 for row in template["variants"])
