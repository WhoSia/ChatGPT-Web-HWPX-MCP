from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.p419_dependency_census import _python_references, census


class DependencyCensusTests(unittest.TestCase):
    def test_static_and_literal_dynamic_imports(self):
        imports = """import alpha
from beta import fn
import importlib
importlib.import_module("gamma")
__import__("delta.helper")
"""
        result = _python_references(imports, {"alpha", "beta", "gamma", "delta"})
        self.assertEqual(result, {"alpha", "beta", "gamma", "delta"})

    def test_backlink_inventory_does_not_claim_unused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "alpha.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "beta.py").write_text("VALUE = 2\n", encoding="utf-8")
            (root / "entry.py").write_text(
                'import alpha\nimport importlib\nimportlib.import_module("beta")\n',
                encoding="utf-8",
            )
            (root / "Dockerfile").write_text("RUN python alpha.py\n", encoding="utf-8")
            report = census(root)
            rows = {row["module"]: row for row in report["modules"]}
            self.assertEqual(report["root_module_count"], 3)
            self.assertEqual(rows["alpha"]["explicit_backlinks"], ["Dockerfile", "entry.py"])
            self.assertEqual(rows["beta"]["explicit_backlinks"], ["entry.py"])
            self.assertEqual(rows["entry"]["explicit_backlinks"], [])
            self.assertEqual(rows["entry"]["review_status"], "REQUIRES_MANUAL_REVIEW")
            self.assertIn("not proof of dead code", report["caution"])

    def test_syntax_errors_do_not_disappear_from_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "good.py").write_text("a = 1\n", encoding="utf-8")
            (root / "bad.py").write_text("def broken(:\n", encoding="utf-8")
            with self.assertRaises(SyntaxError):
                census(root)


if __name__ == "__main__":
    unittest.main()
