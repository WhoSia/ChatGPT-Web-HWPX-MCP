"""P4.21 professional authoring review must never fabricate content."""
from copy import deepcopy

from hwpx_mcp.quality.p421_professional_authoring_review import review_authoring_plan


def test_healthy_report_has_no_static_warnings():
    x = review_authoring_plan({"blocks": [
        {"type": "title", "text": "연구"},
        {"type": "heading", "level": 1, "text": "결과"},
        {"type": "paragraph", "text": "관측"},
        {"type": "table", "caption": "Table 1", "rows": 1, "cols": 1},
    ]})
    assert x["status"] == "NO_STATIC_DESIGN_WARNINGS"
    assert x["native_render_evidence"] == "NOT_OBSERVED"


def test_detects_missing_title_heading_skip_and_unlabeled_object():
    r = review_authoring_plan({"blocks": [
        {"type": "heading", "level": 1, "text": "a"},
        {"type": "heading", "level": 3, "text": "b"},
        {"type": "picture", "content_base64": "unused"},
        {"type": "paragraph", "text": "   "},
    ]})
    codes = {d["code"] for d in r["diagnostics"]}
    assert codes == {"TITLE_HIERARCHY_MISSING", "HEADING_LEVEL_SKIP",
                     "UNLABELED_NATIVE_OBJECT", "EMPTY_TEXT_BLOCK"}


def test_does_not_edit_semantic_plan_or_invent_caption():
    p = {"blocks": [{"type": "title", "text": "기존 제목"},
                    {"type": "equation", "latex": "E=mc^2"}]}
    original = deepcopy(p)
    a = review_authoring_plan(p)
    assert p == original
    assert a == review_authoring_plan(p)
    assert a["mutated_plan"] is False
    assert a["professional_visual_acceptance"] == "NOT_ADJUDICATED"


def test_neighboring_manual_caption_is_accepted():
    r = review_authoring_plan({"blocks": [
        {"type": "title", "text": "리포트"},
        {"type": "table", "rows": 2, "cols": 2},
        {"type": "caption", "text": "표 1"},
    ]})
    assert "UNLABELED_NATIVE_OBJECT" not in {x["code"] for x in r["diagnostics"]}


def test_invalid_plan_rejected():
    import pytest
    for item in (None, {"blocks": "text"}, {"blocks": [None]}):
        with pytest.raises(ValueError):
            review_authoring_plan(item)
