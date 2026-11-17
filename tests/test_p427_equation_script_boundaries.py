import pytest
from hwpx.equation import latex_to_eqedit as native_latex_to_eqedit

from hwpx_mcp.equations.latex_to_eqedit import latex_to_eqedit


@pytest.mark.parametrize(("implicit", "explicit"), [
    (r"S(t)=\sum_{i=1}^{n}p_iS_i(t)", r"S(t)=\sum_{i=1}^{n}p_{i}S_{i}(t)"),
    (r"x_12+y^23", r"x_{1}2+y^{2}3"),
    (r"x^ .2", r"x^{.}2"),
    (r"x_가나", r"x_{가}나"),
    (r"$x_{p_iS}+z^ab$", r"$x_{p_{i}S}+z^{a}b$"),
    (r"\begin{matrix}p_iS & x_12\end{matrix}", r"\begin{matrix}p_{i}S & x_{1}2\end{matrix}"),
])
def test_implicit_script_matches_explicit_single_token_group(implicit, explicit):
    assert latex_to_eqedit(implicit) == native_latex_to_eqedit(explicit)


@pytest.mark.parametrize("source", [
    r"x_{ij}^2+e^{-2x}",
    r"x_\alpha+\vec{x}",
    r"\text{p_iS} + \mathrm{x_12} + \mbox{z^ab} + \textrm{a_iZ}",
])
def test_literal_text_and_existing_groups_keep_their_boundaries(source):
    assert latex_to_eqedit(source) == native_latex_to_eqedit(source)


def test_normalization_resumes_after_literal_with_escaped_brace():
    literal = r"\text{escaped \} p_iS}"
    assert latex_to_eqedit(literal + " + p_iS") == native_latex_to_eqedit(literal + " + p_{i}S")
