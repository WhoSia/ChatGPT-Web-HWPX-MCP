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


if __name__ == "__main__":
    unittest.main()
