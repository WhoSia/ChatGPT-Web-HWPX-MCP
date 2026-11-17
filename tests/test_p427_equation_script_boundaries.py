import tempfile
import unittest
from pathlib import Path

from hwpx.equation import latex_to_eqedit as native_latex_to_eqedit
from hwpx.equation.authoring import UnsupportedLatexError

from hwpx_mcp.document.p210_equations import apply_equation_edits_atomic, build_equation_map
from hwpx_mcp.document.p321_document_composer import compose_document_plan
from hwpx_mcp.equations.latex_to_eqedit import latex_to_eqedit
from hwpx_mcp.interfaces.p426_equation_experience import describe_equation
from hwpx_mcp.rendering.p46_native_authoring import audit_equation_latex


SCRIPT_PAIRS = (
    (r"S(t)=\sum_{i=1}^{n}p_iS_i(t)", r"S(t)=\sum_{i=1}^{n}p_{i}S_{i}(t)"),
    (r"x_12+y^23", r"x_{1}2+y^{2}3"),
    (r"x^ .2", r"x^{.}2"),
    (r"x_가나", r"x_{가}나"),
    (r"$x_{p_iS}+z^ab$", r"$x_{p_{i}S}+z^{a}b$"),
    (r"\begin{matrix}p_iS & x_12\end{matrix}", r"\begin{matrix}p_{i}S & x_{1}2\end{matrix}"),
)


class P427EquationScriptBoundaryTests(unittest.TestCase):
    def test_implicit_script_matches_explicit_single_token_group(self):
        for implicit, explicit in SCRIPT_PAIRS:
            with self.subTest(source=implicit):
                self.assertEqual(latex_to_eqedit(implicit), native_latex_to_eqedit(explicit))

    def test_literal_text_and_existing_groups_keep_their_boundaries(self):
        for source in (
            r"x_{ij}^2+e^{-2x}",
            r"x_\alpha+\vec{x}",
            r"\text{p_iS} + \mathrm{x_12} + \mbox{z^ab} + \textrm{a_iZ}",
        ):
            with self.subTest(source=source):
                self.assertEqual(latex_to_eqedit(source), native_latex_to_eqedit(source))

    def test_normalization_resumes_after_literal_with_escaped_brace(self):
        literal = r"\text{escaped \} p_iS}"
        self.assertEqual(
            latex_to_eqedit(literal + " + p_iS"),
            native_latex_to_eqedit(literal + " + p_{i}S"),
        )

    def test_missing_script_argument_is_rejected(self):
        for source in (r"x_", r"$x^$", r"x_^2", r"{x_}", r"\begin{matrix}x_&y\end{matrix}"):
            with self.subTest(source=source):
                with self.assertRaisesRegex(UnsupportedLatexError, "missing LaTeX argument"):
                    latex_to_eqedit(source)

        self.assertFalse(audit_equation_latex("x_")["supported"])
        with self.assertRaisesRegex(ValueError, "LATEX_TO_EQEDIT_UNSUPPORTED"):
            describe_equation("x^")

    def test_duplicate_script_on_same_base_is_rejected(self):
        for source, kind in (
            (r"x^2^3", "superscript"),
            (r"x^\alpha^\beta", "superscript"),
            (r"x_1^2_3", "subscript"),
            (r"x^{a_j_k}", "subscript"),
            (r"\begin{cases}x_i^2^3 & x>0\end{cases}", "superscript"),
        ):
            with self.subTest(source=source):
                with self.assertRaisesRegex(UnsupportedLatexError, f"duplicate LaTeX {kind}"):
                    latex_to_eqedit(source)

    def test_distinct_bases_and_nested_scripts_keep_their_native_output(self):
        for source in (
            r"x_i^2+x^2_i",
            r"x^{2^3}+x_{i_j}",
            r"{x^2}^3+x^2{}^3",
            r"\left(x^2\right)^3",
            r"\begin{matrix}x^2&{}^3\\x_i&{}_{j}\end{matrix}",
            r"\text{x^2^3 and p_i_j}",
        ):
            with self.subTest(source=source):
                self.assertEqual(latex_to_eqedit(source), native_latex_to_eqedit(source))

    def test_duplicate_scripts_do_not_generate_a_document(self):
        invalid = r"x^2^3"
        audit = audit_equation_latex(invalid)
        self.assertFalse(audit["supported"])
        self.assertIn("duplicate LaTeX superscript", audit["unsupported"]["detail"])
        with self.assertRaisesRegex(ValueError, "LATEX_TO_EQEDIT_UNSUPPORTED.*duplicate"):
            describe_equation(invalid)

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "new.hwpx"
            for block in (
                {"type": "equation", "latex": invalid},
                {"type": "equation_line", "parts": [{"latex": "x_i"}, {"latex": invalid}]},
                {"type": "piecewise", "rows": [{"expression": "1", "condition": invalid}]},
            ):
                with self.subTest(block=block):
                    with self.assertRaisesRegex(UnsupportedLatexError, "duplicate LaTeX superscript"):
                        compose_document_plan(path, {"blocks": [{"type": "paragraph", "text": "Text"}, block]})
                    self.assertEqual(list(Path(folder).iterdir()), [])

    def test_inspection_creation_and_replacement_agree_on_saved_script(self):
        implicit, explicit = SCRIPT_PAIRS[0]
        expected = native_latex_to_eqedit(explicit)
        self.assertEqual(describe_equation(implicit)["eqedit_script"], expected)
        self.assertEqual(audit_equation_latex(implicit)["eqedit_script"], expected)

        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "equations.hwpx"
            compose_document_plan(file, {"blocks": [
                {"type": "equation", "latex": implicit},
                {"type": "equation_line", "parts": [{"latex": implicit}, {"text": ", "}]},
                {"type": "piecewise", "rows": [{"expression": implicit, "condition": "t>0"}]},
                {"type": "equation", "latex": "x"},
            ]})
            saved = build_equation_map(file)["equations"]
            locator = saved[-1]["locator"]
            operation = {"op": "replace_equation", "equation": locator, "latex": implicit}
            apply_equation_edits_atomic(file, [operation], expected_revision=1, current_revision=1)
            saved = build_equation_map(file)["equations"]
            self.assertEqual([item["script"] for item in saved], [
                expected, expected, f"cases {{{expected} & t > 0}}", expected,
            ])
            self.assertEqual(saved[-1]["locator"], locator)

            before = file.read_bytes()
            for invalid in ("x^", "x^2^3"):
                with self.subTest(latex=invalid):
                    with self.assertRaises(UnsupportedLatexError):
                        apply_equation_edits_atomic(
                            file, [dict(operation, latex="y"), dict(operation, latex=invalid)],
                            expected_revision=2, current_revision=2,
                        )
                    self.assertEqual(file.read_bytes(), before)
