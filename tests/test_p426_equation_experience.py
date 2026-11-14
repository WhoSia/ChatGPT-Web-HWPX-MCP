"""P4.26 real EqEdit conversion and saved native HWPX equation corpus."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from hwpx_mcp.interfaces.p426_equation_experience import (
    describe_equation, register_equation_experience,
)
from hwpx_mcp.orchestration.p338_rich_builder import compile_rich_document_plan
from hwpx_mcp.document.p321_document_composer import compose_document_plan

DOC = "doc_" + "d" * 24
OWNER = "equation-test-owner"


class FakeMcp:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def register(f):
            self.tools[f.__name__] = f
            return f
        return register


class EquationExperienceTests(unittest.TestCase):
    def test_equation_families_compile_to_actual_eqedit_scripts(self):
        formulas = [
            "V=IR",
            r"\frac{a+b}{c}",
            r"\sqrt{x^2+y^2}",
            r"\sum_{i=1}^{n} i",
            r"\int_0^1 x^2 dx",
            r"\begin{matrix}a&b\\c&d\end{matrix}",
        ]
        for latex in formulas:
            with self.subTest(latex=latex):
                info = describe_equation(latex)
                self.assertTrue(info["eqedit_script"].strip())
                self.assertEqual(len(info["eqedit_script_sha256"]), 64)
                self.assertTrue(info["editable_in_hancom"])
                self.assertFalse(info["native_render_verified"])

    def test_unsupported_spacing_macro_is_explicit_not_silently_removed(self):
        with self.assertRaisesRegex(ValueError, "LATEX_TO_EQEDIT_UNSUPPORTED"):
            describe_equation(r"\\int_0^1 x^2\\,dx")

    def test_empty_latex_refused(self):
        with self.assertRaisesRegex(ValueError, "LATEX_EQUATION_INVALID"):
            describe_equation(" ")

    def test_read_real_saved_native_equation_script(self):
        plan = compile_rich_document_plan({
            "preset": "academic-report",
            "sections": [{"blocks": [
                {"type": "title", "text": "수식 확인"},
                {"type": "equation", "latex": r"\frac{a}{b}"},
            ]}],
        })
        with tempfile.TemporaryDirectory(prefix="p426-equations-") as tmp:
            path = Path(tmp) / "test.hwpx"
            receipt = compose_document_plan(path, plan["plan"])
            self.assertTrue(receipt["atomic_commit"])
            payload = path.read_bytes()

        mcp = FakeMcp()
        row = {"owner_subject": OWNER, "revision": 1, "bytes": payload}
        core = SimpleNamespace(
            mcp=mcp,
            _caller_subject=lambda: OWNER,
            _paths=lambda id: (id, None),
            DOCUMENT_STORE=SimpleNamespace(load_current=lambda id: row),
        )
        register_equation_experience(core)
        result = mcp.tools["inspect_document_equations"](DOC)
        self.assertEqual(result["equation_count"], 1)
        self.assertTrue(result["equations"][0]["script"])
        self.assertEqual(len(result["equation_script_custody_sha256"]), 64)

    def test_equation_ownership_blocks_disclosure(self):
        mcp = FakeMcp()
        core = SimpleNamespace(
            mcp=mcp,
            _caller_subject=lambda: OWNER,
            _paths=lambda doc: doc,
            DOCUMENT_STORE=SimpleNamespace(
                load_current=lambda doc: {"owner_subject": "not-owner", "revision": 1}),
        )
        register_equation_experience(core)
        with self.assertRaises(FileNotFoundError):
            mcp.tools["inspect_document_equations"](DOC)

if __name__ == "__main__":
    unittest.main()
