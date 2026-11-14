"""P4.27 R4: authenticated MCP-bound native preservation write path.

Uses an in-process owned document and real saved HWPX. Only ownership and
metadata persistence are substituted so that production validation and
transaction logic are genuinely exercised without a network or database.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from hwpx import HwpxDocument

# The native-only acceptance runner has no OAuth/Postgres service; the
# authenticated server test is executed independently in the Postgres job.
if os.environ.get("P12_AUTH_DATABASE_URL") and os.environ.get("P12_STATE_SECRET"):
    import server_p2 as api
else:
    api = None
from hwpx_mcp.document.p323_advanced_tables import build_advanced_table_map


@unittest.skipUnless(api is not None, "requires authenticated PostgreSQL server")
class PreservedEditMcpAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="p427-r4-mcp-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "owned-original.hwpx"
        doc = HwpxDocument.new()
        doc.add_paragraph("Unrelated user prose")
        table = doc.add_table(rows=2, cols=2)
        table.set_cell_text(0, 0, "Read-only neighbor")
        table.set_cell_text(0, 1, "Editable target")
        table.set_cell_text(1, 0, "Other cell")
        table.set_cell_text(1, 1, "Final cell")
        doc.save_to_path(str(self.path))
        doc.close()
        self.metadata = {"revision": 4, "source": "native"}
        self.refresh = Mock()
        self.real_owned_document = api._owned_document
        self.auth = patch.object(
            api, "_owned_document", return_value=(self.metadata, self.path),
        )
        self.save = patch.object(api, "_refresh_metadata", self.refresh)
        self.auth.start()
        self.save.start()
        self.addCleanup(self.auth.stop)
        self.addCleanup(self.save.stop)
        self.table = build_advanced_table_map(self.path)["tables"][0]

    def _operation(self):
        cell = next(
            c for c in self.table["cells"] if (c["row"], c["col"]) == (0, 1)
        )
        return {
            "op": "set_cell_text", "table": self.table["locator"],
            "cell": cell["locator"], "text": "New verified value",
        }

    def digest(self):
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def test_real_mcp_entrypoint_commits_with_validation_and_receipts(self):
        before = self.digest()
        response = api.apply_preserved_table_edit(
            "owned-user-document", 4, self._operation()
        )
        self.assertTrue(response["ok"])
        self.assertEqual(response["revision_before"], 4)
        self.assertEqual(response["revision_after"], 5)
        self.assertEqual(self.metadata["revision"], 5)
        self.assertEqual(response["preservation_grade"], "TARGETED_PARTS_ONLY")
        self.assertEqual(response["sha256"], self.digest())
        self.assertNotEqual(before, self.digest())
        self.assertEqual(response["preserved_edit"]["semantic_preservation"]["unapproved_table_changes"], 0)
        self.assertEqual(response["preserved_edit"]["table_anchor_paragraphs_verified"], 1)
        self.assertTrue(response["validation"]["valid"])
        self.refresh.assert_called_once()
        self.assertEqual(
            next(c for c in build_advanced_table_map(self.path)["tables"][0]["cells"]
                 if (c["row"], c["col"]) == (0, 1))["text"],
            "New verified value",
        )

    def test_stale_revision_and_invalid_operation_dont_write_or_refresh(self):
        original = self.digest()
        with self.assertRaisesRegex(ValueError, "Stale revision"):
            api.apply_preserved_table_edit("owned-user-document", 3, self._operation())
        with self.assertRaisesRegex(ValueError, "R3_EDIT_OPERATION_NOT_ADMITTED"):
            api.apply_preserved_table_edit(
                "owned-user-document", 4,
                {"op": "delete_table", "table": self.table["locator"]},
            )
        self.assertEqual(self.digest(), original)
        self.assertEqual(self.metadata["revision"], 4)
        self.refresh.assert_not_called()

    def test_owner_gate_precedes_native_edit(self):
        original = self.digest()
        with patch.object(api, "_owned_document", side_effect=PermissionError("owner rejected")):
            with self.assertRaisesRegex(PermissionError, "owner rejected"):
                api.apply_preserved_table_edit("foreign-user-document", 4, self._operation())
        self.assertEqual(self.digest(), original)
        self.refresh.assert_not_called()

    def test_real_owner_identity_check_blocks_foreign_caller(self):
        original = self.digest()
        alien_owned_metadata = {
            "revision": 4, "source": "native",
            "owner_subject": "authorized-document-owner",
        }
        with (
            patch.object(api, "_owned_document", side_effect=self.real_owned_document),
            patch.object(api.core, "_load_metadata", return_value=alien_owned_metadata),
            patch.object(api.core, "_caller_subject", return_value="foreign-subject"),
        ):
            with self.assertRaisesRegex(PermissionError, "not owned"):
                api.apply_preserved_table_edit(
                    "any-owned-document", 4, self._operation(),
                )
        self.assertEqual(self.digest(), original)
        self.assertEqual(self.metadata["revision"], 4)
        self.refresh.assert_not_called()

    def test_package_validator_failure_refuses_commit_and_revision_bump(self):
        original = self.digest()
        with patch.object(api.core, "validate_hwpx_package",
                          side_effect=ValueError("TEST_PACKAGE_REJECTED")):
            with self.assertRaisesRegex(ValueError, "TEST_PACKAGE_REJECTED"):
                api.apply_preserved_table_edit(
                    "owned-user-document", 4, self._operation()
                )
        self.assertEqual(self.digest(), original)
        self.assertEqual(self.metadata["revision"], 4)
        self.refresh.assert_not_called()


if __name__ == "__main__":
    unittest.main()
