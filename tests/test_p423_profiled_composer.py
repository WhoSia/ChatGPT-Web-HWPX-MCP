"""End-to-end HWPX composition under explicit portable style profiles."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hwpx_mcp.document.p321_document_composer import (
    compose_document_plan, document_plan_contract, validate_document_plan,
)


def _plan(*, profile=None):
    plan = {
        "preset": "school-report",
        "blocks": [
            {"id": "heading", "type": "title", "text": "MRI 보고서"},
            {"id": "body", "type": "paragraph", "text": "기존 내용과 수식을 보존한다."},
            {"id": "eq", "type": "equation", "latex": "E=mc^2"},
        ],
    }
    if profile is not None:
        plan["style_profile"] = profile
    return plan


class P423ProfiledComposerTests(unittest.TestCase):
    def test_contract_exposes_style_profile(self):
        contract = document_plan_contract()
        self.assertIn("style_profile", contract["top_level"])
        self.assertEqual(contract["top_level"]["style_profile"]["persistence"], "supplied per task; no implicit storage or automatic learning")

    def test_profile_and_default_both_emit_native_documents(self):
        profile = {"name": "MRI", "roles": {"body": {"run": {"size": 12}, "paragraph": {"line_spacing_percent": 180}}}}
        with tempfile.TemporaryDirectory() as directory:
            vanilla = Path(directory) / "vanilla.hwpx"
            personalized = Path(directory) / "personalized.hwpx"
            before = compose_document_plan(vanilla, _plan())
            after = compose_document_plan(personalized, _plan(profile=profile))
            self.assertTrue(vanilla.is_file())
            self.assertTrue(personalized.is_file())
            self.assertIsNone(before["style_profile_sha256"])
            self.assertEqual(len(after["style_profile_sha256"]), 64)
            self.assertEqual(before["document"]["semantic_sha256"], after["document"]["semantic_sha256"])
            self.assertNotEqual(before["document"]["formatting_sha256"], after["document"]["formatting_sha256"])


if __name__ == "__main__":
    unittest.main()
