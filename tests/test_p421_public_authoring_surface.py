"""P4.21 public MCP create/edit quality response compatibility gates."""
import ast
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1] / "server_p2.py"


def functions():
    module = ast.parse(SERVER.read_text(encoding="utf-8"))
    return {n.name: n for n in module.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def source(name):
    text = SERVER.read_text(encoding="utf-8")
    return ast.get_source_segment(text, functions()[name])


def test_public_creation_exposes_review_and_quality_without_new_arguments():
    fn = functions()["_product_create_impl"]
    value = ast.get_source_segment(SERVER.read_text(encoding="utf-8"), fn)
    assert 'created.get("composition")' in value
    assert '"professional_plan_review": review' in value
    assert '"quality_after_creation": quality' in value
    public = functions()["create_and_deliver_document"]
    assert [a.arg for a in public.args.args][:3] == ["plan", "filename", "request_id"]


def test_both_public_edit_paths_report_before_and_after_quality():
    for name in ("edit_document_and_deliver", "edit_and_deliver_document"):
        s = source(name)
        assert 'before = _p421_public_quality(document_id)' in s
        assert '_p421_quality_diff(before, _p421_public_quality(document_id))' in s
        assert '"quality_comparison": quality' in s
        assert s.index("before = _p421_public_quality") < s.index("edited = apply_edits")


def test_quality_observation_is_read_only_and_fails_nonblocking():
    s = source("_p421_public_quality")
    assert "judge_document_quality(source)" in s
    assert '"QUALITY_OBSERVATION_UNAVAILABLE"' in s
    assert '"release_eligible": False' in s
    assert "apply_edits" not in s


def test_diff_no_fake_visual_or_semantic_pass():
    s = source("_p421_quality_diff")
    assert '"NOT_CERTIFIED_FOR_USER_AUTHORED_EDITS"' in s
    assert '"NOT_OBSERVED"' in s
    assert '"count_delta"' in s


def test_professional_formatting_preview_is_read_only_and_revisioned():
    s = source("preview_professional_formatting")
    assert 'metadata.get("composition_receipt")' in s
    assert '"professional_plan_review"' in s
    assert '"quality_before": _p421_public_quality(document_id)' in s
    assert '"automatic_repairs_applied": False' in s
    assert '"revision": int(metadata["revision"])' in s
    assert "apply_formatting(" not in s


def test_explicit_formatting_returns_before_after_comparison():
    s = source("apply_formatting")
    assert "quality_before = _p421_public_quality(document_id)" in s
    assert "quality_after = _p421_public_quality(document_id)" in s
    assert '"quality_comparison": _p421_quality_diff(quality_before, quality_after)' in s
    assert s.index("quality_before =") < s.index("transaction = apply_rich_formatting_atomic")
    assert '"explicit_user_operations": len(operations)' in s
