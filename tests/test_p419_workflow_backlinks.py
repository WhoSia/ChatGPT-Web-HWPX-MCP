"""P4.20 CI path audit regression, including zero-discovery traps."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.p419_layout_audit import workflow_backlink_errors


class WorkflowBacklinkTests(unittest.TestCase):
    def _fixture(self, source: str) -> Path:
        root = Path(self.tempdir.name)
        dest = root / ".github" / "workflows"
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "layout.yml").write_text(source, encoding="utf-8")
        packaged = root / "hwpx_mcp" / "document" / "p317_page_geometry.py"
        packaged.parent.mkdir(parents=True, exist_ok=True)
        packaged.write_text("VALUE = True\n", encoding="utf-8")
        return root

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tempdir.cleanup()

    def test_rejects_stale_compile_target(self):
        root = self._fixture("run: python -m compileall -q p317_page_geometry.py\n")
        errors = workflow_backlink_errors(root, {"p317_page_geometry"})
        self.assertTrue(any("p317_page_geometry.py" in error[2] for error in errors))

    def test_rejects_stale_path_trigger(self):
        root = self._fixture('paths:\n  - "p317_page_geometry.py"\n')
        self.assertIn(("layout.yml", 2, "p317_page_geometry.py"),
                      workflow_backlink_errors(root, {"p317_page_geometry"}))

    def test_rejects_discover_pattern_that_runs_zero_tests(self):
        root = self._fixture(
            "run: python -m unittest discover -s tests -p tests/test_p419_layout_audit.py -v\n"
        )
        errors = workflow_backlink_errors(root, {"p317_page_geometry"})
        self.assertTrue(any(e[2] == "BROKEN_DISCOVER_PATTERN" for e in errors))

    def test_accepts_new_package_path_and_valid_discover_pattern(self):
        root = self._fixture(
            "run: python -m compileall -q hwpx_mcp/document/p317_page_geometry.py\n"
            "run: python -m unittest discover -s tests -p test_p419_layout_audit.py -v\n"
        )
        self.assertEqual(workflow_backlink_errors(root, {"p317_page_geometry"}), [])


if __name__ == "__main__":
    unittest.main()
