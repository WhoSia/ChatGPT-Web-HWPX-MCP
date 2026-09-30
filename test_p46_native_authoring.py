from p46_native_authoring import (
    audit_equation_latex,
    compile_native_authoring_bundle,
    equation_capability_matrix,
    native_authoring_contract,
)


def test_equation_supported_and_style_abstention():
    supported = audit_equation_latex(r"\\begin{pmatrix} a & b \\ c & d \\end{pmatrix}")
    assert supported["supported"] is True
    assert supported["status"] == "NATIVE_EQEDIT_VERIFIED_TOKEN_SET"

    blackboard = audit_equation_latex(r"\\mathbb{R}")
    calligraphic = audit_equation_latex(r"\\mathcal{F}")
    assert blackboard["supported"] is False
    assert blackboard["status"] == "UNSUPPORTED_MATH_STYLE"
    assert blackboard["unsupported"]["feature"] == "BLACKBOARD_BOLD"
    assert calligraphic["unsupported"]["feature"] == "CALLIGRAPHIC"
    assert "NO_AUTOMATIC_IMAGE" in blackboard["fallback"]


def test_matrix_reports_abstention_without_silent_approximation():
    matrix = equation_capability_matrix([
        r"\\frac{1}{2}",
        r"\\begin{cases} x & x>0 \\ 0 & x\\leq0 \\end{cases}",
        r"\\begin{align} x&=1 \\end{align}",
        r"\\widehat{xy}",
    ])
    assert matrix["probe_count"] == 4
    assert matrix["supported_count"] == 2
    assert matrix["abstained_count"] == 2
    assert matrix["policy"] == "MEASURE_NATIVE_CAPABILITY_THEN_FAIL_CLOSED"


def test_bundle_compiler_resolves_first_body_and_blocks_unsupported_math():
    document_map = {"paragraphs": [{"locator": "p_anchor", "text": "Anchor"}]}
    ready = compile_native_authoring_bundle({
        "equations": [{"op": "insert_equation", "paragraph": "first_body", "latex": r"\\frac{a}{b}"}],
        "tables": [{"op": "create_table", "rows": 2, "cols": 2}],
    }, document_map=document_map)
    assert ready["ready"] is True
    assert ready["execution_bundle"]["equations"][0]["paragraph"] == "p_anchor"
    assert ready["execution_semantics"] == "ONE_CALL_ONE_DURABLE_REVISION_ALL_OR_NOTHING"

    blocked = compile_native_authoring_bundle({
        "equations": [{"op": "insert_equation", "paragraph": "first_body", "latex": r"\\mathcal{F}"}],
    }, document_map=document_map)
    assert blocked["ready"] is False
    assert blocked["blockers"][0]["reason"] == "UNSUPPORTED_MATH_STYLE"


def test_contract_keeps_surface_small():
    contract = native_authoring_contract()
    assert contract["phase"] == "P4.6"
    assert contract["product"] == "0.32.0-p4.6"
    assert len(contract["high_level_tools"]) == 5
    assert "LOW_LEVEL_TOOLS_REMAIN_ESCAPE_HATCHES" in contract["principles"]
