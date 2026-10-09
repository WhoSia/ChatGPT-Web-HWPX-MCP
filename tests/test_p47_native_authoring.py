from hwpx_mcp.rendering.p47_native_authoring import (
    adjudicate_equation_render_evidence,
    authoring_v2_contract,
    compile_unified_authoring_plan,
    equation_render_frontier,
)


def test_frontier_keeps_candidates_unpromoted():
    frontier = equation_render_frontier()
    assert frontier["candidate_count"] >= 8
    assert frontier["production_raw_eqedit"] == "CLOSED"
    by_id = {x["candidate_id"]: x for x in frontier["candidates"]}
    assert by_id["bold"]["promotion_target"] == r"\mathbf"
    assert by_id["eqalign"]["promotion_target"] == "LATEX_ALIGN_FAMILY"
    assert all(x["production_authoring_status"] == "NOT_PROMOTED" for x in frontier["candidates"])


def test_no_receipt_means_no_promotion():
    result = adjudicate_equation_render_evidence(None)
    assert result["status"] == "WORLD_CONTACT_PENDING"
    assert result["promotion_eligible"] == []
    assert "bold" in result["held"]


def test_adjudication_requires_native_and_human_evidence():
    frontier = equation_render_frontier()
    rows = []
    for spec in frontier["candidates"]:
        rows.append({
            "candidate_id": spec["candidate_id"],
            "export_succeeded": True,
            "candidate_visual_difference_observed": spec["candidate_id"] == "bold",
            "semantic_intent_match": spec["candidate_id"] == "bold",
            "no_clipping_or_corruption": True,
            "human_visual_status": "PASS" if spec["candidate_id"] == "bold" else "PENDING",
            "control_hwpx_sha256": "a" * 64,
            "candidate_hwpx_sha256": "b" * 64,
            "control_pdf_sha256": "c" * 64,
            "candidate_pdf_sha256": "d" * 64,
        })
    result = adjudicate_equation_render_evidence({
        "frontier_sha256": frontier["frontier_sha256"],
        "renderer": {"hancom_native": True, "os": "Windows 11", "executable_sha256": "e" * 64},
        "candidates": rows,
    })
    assert result["promotion_eligible"] == ["bold"]
    assert "eqalign" in result["held"]
    assert result["promotion_requires_code_change"] is True


def test_unified_plan_keeps_private_candidate_semantics():
    compiled = compile_unified_authoring_plan({
        "rich_plan": {
            "sections": [{
                "blocks": [
                    {"type": "heading", "text": "결과"},
                    {"type": "paragraph", "text": "본문"},
                    {"type": "equation", "latex": r"\frac{a}{b}"},
                ]
            }]
        },
        "native_bundle": {
            "drawings": [{"op": "insert_rectangle", "anchor": "first_body", "width": 7200, "height": 3600}]
        },
    })
    assert compiled["native_operation_count"] == 1
    assert "REVISION_1_COMMIT" in compiled["creation_semantics"]


def test_contract_surface_stays_small():
    contract = authoring_v2_contract()
    assert contract["product"] == "0.33.0-p4.7"
    assert len(contract["high_level_tools"]) == 5
    assert "RAW_EQEDIT_PRODUCTION_GATE_REMAINS_CLOSED" in contract["invariants"]
