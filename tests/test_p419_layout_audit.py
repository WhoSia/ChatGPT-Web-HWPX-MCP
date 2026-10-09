"""Behavioral regression for the P4.20 relocated-module backlink gate."""
from __future__ import annotations

import unittest

from scripts.p419_layout_audit import stale_root_imports


class RootBacklinkAuditTests(unittest.TestCase):
    RETIRED = {"p347_trust", "p342_corpus_evidence", "p333_file_delivery"}

    def test_direct_imports_and_from_imports_are_rejected(self):
        text = (
            "import p347_trust as trust\n"
            "from p342_corpus_evidence import evidence\n"
            "import p333_file_delivery.helpers\n"
        )
        self.assertEqual(stale_root_imports(text, self.RETIRED), self.RETIRED)

    def test_builtin_import_and_importlib_aliases_are_rejected(self):
        text = (
            "import importlib as loader\n"
            "from importlib import import_module as load\n"
            "__import__('p347_trust')\n"
            "loader.import_module('p342_corpus_evidence')\n"
            "load('p333_file_delivery')\n"
        )
        self.assertEqual(stale_root_imports(text, self.RETIRED), self.RETIRED)

    def test_runpy_and_find_spec_backlinks_are_rejected(self):
        text = (
            "import runpy as runner\n"
            "import importlib.util as iutil\n"
            "from importlib.util import find_spec as locate\n"
            "runner.run_module('p347_trust')\n"
            "iutil.find_spec('p342_corpus_evidence')\n"
            "locate('p333_file_delivery')\n"
        )
        self.assertEqual(stale_root_imports(text, self.RETIRED), self.RETIRED)

    def test_qualified_imports_and_unrelated_methods_are_accepted(self):
        text = (
            "from hwpx_mcp.extensions.p347_trust import verify\n"
            "import hwpx_mcp.corpus.p342_corpus_evidence\n"
            "thing.import_module('p347_trust')\n"
            "thing.find_spec('p342_corpus_evidence')\n"
            "def arbitrary():\n"
            "    return 'p333_file_delivery'\n"
        )
        self.assertEqual(stale_root_imports(text, self.RETIRED), set())

    def test_relative_import_not_mistaken_for_removed_root(self):
        self.assertEqual(
            stale_root_imports("from .p347_trust import verify\n", self.RETIRED),
            set(),
        )

    def test_computed_import_is_not_falsely_claimed_detected(self):
        self.assertEqual(
            stale_root_imports(
                "import importlib\n"
                "module = 'p347_' + 'trust'\n"
                "importlib.import_module(module)\n",
                self.RETIRED,
            ),
            set(),
        )

    def test_invalid_python_is_not_silently_skipped(self):
        with self.assertRaises(SyntaxError):
            stale_root_imports("from p347_trust import (\n", self.RETIRED)


if __name__ == "__main__":
    unittest.main()
