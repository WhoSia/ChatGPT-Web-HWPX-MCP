"""P4.27 MCP tool acceptance with native files and a real PostgreSQL store."""
from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import patch
from urllib.parse import urlsplit

from starlette.requests import Request

from hwpx import HwpxDocument
from hwpx.equation.authoring import UnsupportedLatexError

# The native-only acceptance runner has no OAuth/Postgres service; the
# authenticated server test is executed independently in the Postgres job.
if os.environ.get("P12_AUTH_DATABASE_URL") and os.environ.get("P12_STATE_SECRET"):
    import server_p2 as api
else:
    api = None
from hwpx_mcp.document.p210_equations import build_equation_map
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
        table.cell(0, 1).paragraphs[0].add_equation("a + b")
        table.set_cell_text(1, 0, "Other cell")
        table.set_cell_text(1, 1, "Final cell")
        doc.save_to_path(str(self.path))
        doc.close()
        self.owner = "p427-acceptance-owner"
        self.store = api.core.DOCUMENT_STORE
        self.seed_saved_document()
        caller = patch.object(api.core, "_caller_subject", return_value=self.owner)
        caller.start()
        self.addCleanup(caller.stop)
        self.load_metadata = api.core._load_metadata
        cache = patch.object(api.core, "_load_metadata",
                             side_effect=AssertionError("preserved edit touched the shared cache"))
        cache.start()
        self.addCleanup(cache.stop)
        self.table = build_advanced_table_map(self.path)["tables"][0]

    def seed_saved_document(self):
        self.document_id = api.core._new_document_id()
        self.addCleanup(self.store.delete_document, self.document_id)
        self.initial_bytes = self.path.read_bytes()
        validation = api.core.validate_hwpx_package(self.path)
        metadata = api.core._metadata(
            self.document_id, filename="acceptance.hwpx", owner_subject=self.owner,
            validation=validation, source="native",
        )
        self.store.put_revision(
            document_id=self.document_id, owner_subject=self.owner,
            revision=1, expected_revision=0, data=self.initial_bytes,
            metadata=metadata, expires_at_epoch=time.time() + 300,
        )

    def _operation(self):
        cell = next(
            c for c in self.table["cells"] if (c["row"], c["col"]) == (0, 1)
        )
        return {
            "op": "set_cell_text", "table": self.table["locator"],
            "cell": cell["locator"], "text": "New verified value",
        }

    def digest(self):
        row = self.store.load_current(self.document_id)
        self.path.write_bytes(row["bytes"])
        return hashlib.sha256(row["bytes"]).hexdigest()

    def test_real_mcp_entrypoint_commits_with_validation_and_receipts(self):
        before = self.digest()
        response = api.apply_preserved_table_edit(
            self.document_id, 1, self._operation()
        )
        self.assertTrue(response["ok"])
        self.assertEqual(response["revision_before"], 1)
        self.assertEqual(response["revision_after"], 2)
        self.assertEqual(self.store.load_current(self.document_id)["revision"], 2)
        self.assertEqual(response["preservation_grade"], "TARGETED_PARTS_ONLY")
        self.assertEqual(response["sha256"], self.digest())
        self.assertNotEqual(before, self.digest())
        self.assertEqual(response["preserved_edit"]["semantic_preservation"]["unapproved_table_changes"], 0)
        self.assertEqual(response["preserved_edit"]["table_anchor_paragraphs_verified"], 1)
        self.assertTrue(response["validation"]["valid"])
        self.assertEqual(response["preserved_edit"]["unrelated_cells_verified"], 3)
        self.assertEqual(response["preserved_edit"]["target_cell_inline_objects_verified"], 1)
        self.assertEqual([item["script"] for item in build_equation_map(self.path)["equations"]],
                         ["a + b"])
        self.assertEqual(response["preserved_edit"]["committed_sha256"], response["sha256"])
        self.assertEqual(response["preserved_edit"]["mutation_footprint"]["observed"]["changed_parts"],
                         [self.table["section_path"]])
        self.assertEqual(
            next(c for c in build_advanced_table_map(self.path)["tables"][0]["cells"]
                 if (c["row"], c["col"]) == (0, 1))["text"],
            "New verified value",
        )

    def test_duplicate_equation_rejects_a_batch_without_a_new_durable_revision(self):
        before = self.store.load_current(self.document_id)
        locator = build_equation_map(self.path)["equations"][0]["locator"]
        valid = {"op": "replace_equation", "equation": locator, "latex": "x^{2^3}"}
        invalid = dict(valid, latex="x^2^3")
        self.addCleanup(api.core._delete_document_files, self.document_id)

        # Equation editing uses the existing authenticated hydration path.
        with patch.object(api.core, "_load_metadata", self.load_metadata):
            with self.assertRaisesRegex(UnsupportedLatexError, "duplicate LaTeX superscript"):
                api.apply_equation_edits(self.document_id, 1, [valid, invalid])

            unchanged = self.store.load_current(self.document_id)
            self.assertEqual(unchanged["revision"], 1)
            self.assertEqual(unchanged["bytes"], before["bytes"])
            local_path, _ = api.core._paths(self.document_id)
            self.assertEqual(local_path.read_bytes(), before["bytes"])

            result = api.apply_equation_edits(self.document_id, 1, [valid])
            stored = self.store.load_current(self.document_id)
            self.assertEqual(result["revision_after"], 2)
            self.assertEqual(stored["revision"], 2)
            self.assertEqual(stored["sha256"], result["sha256"])
            self.assertEqual(self.digest(), stored["sha256"])
            self.assertEqual(build_equation_map(self.path)["equations"][0]["script"], "x ^{2 ^{3}}")

    def test_incomplete_command_preserves_revision_and_shorthand_fraction_commits(self):
        before = self.store.load_current(self.document_id)
        locator = build_equation_map(self.path)["equations"][0]["locator"]
        valid = {"op": "replace_equation", "equation": locator, "latex": r"\frac12"}
        self.addCleanup(api.core._delete_document_files, self.document_id)

        with patch.object(api.core, "_load_metadata", self.load_metadata):
            for latex in (r"\frac{x}", r"\sqrt[2]"):
                with self.subTest(latex=latex):
                    with self.assertRaisesRegex(UnsupportedLatexError, "missing LaTeX argument"):
                        api.apply_equation_edits(self.document_id, 1, [valid, dict(valid, latex=latex)])
                    unchanged = self.store.load_current(self.document_id)
                    self.assertEqual(unchanged["revision"], 1)
                    self.assertEqual(unchanged["bytes"], before["bytes"])

            result = api.apply_equation_edits(self.document_id, 1, [valid])
            self.assertEqual(result["revision_after"], 2)
            self.assertEqual(result["sha256"], self.digest())
            self.assertEqual(build_equation_map(self.path)["equations"][0]["script"], "{1} over {2}")

    def test_phrase_edit_through_mcp_keeps_existing_equation(self):
        operation = self._operation()
        del operation["text"]
        operation.update(
            op="replace_cell_phrase", paragraph_index=0,
            old_text="Editable", new_text="Reviewed",
        )
        response = api.apply_preserved_table_edit(self.document_id, 1, operation)
        self.assertEqual(response["revision_after"], 2)
        self.assertEqual(response["preserved_edit"]["operation"], "replace_cell_phrase")
        self.assertEqual(response["preserved_edit"]["target_cell_inline_objects_verified"], 1)
        self.assertEqual(response["sha256"], self.digest())
        cells = build_advanced_table_map(self.path)["tables"][0]["cells"]
        self.assertEqual(next(cell["text"] for cell in cells
                              if cell["locator"] == operation["cell"]), "Reviewed target")
        self.assertEqual([item["script"] for item in build_equation_map(self.path)["equations"]],
                         ["a + b"])

    def test_preserved_edit_and_delivery_are_registered_mcp_tools(self):
        tools = {tool.name: tool for tool in asyncio.run(api.core.mcp.list_tools())}
        self.assertIn("apply_preserved_table_edit", tools)
        schema = tools["edit_preserved_table_and_deliver"].input_schema
        self.assertEqual(set(schema["required"]), {"document_id", "expected_revision", "operation"})

    def download(self, result):
        link = next(item for item in result.content if item.type == "resource_link")
        url = urlsplit(str(link.uri))
        request = Request({
            "type": "http", "method": "GET", "path": url.path,
            "query_string": url.query.encode(), "headers": [],
            "path_params": {"document_id": self.document_id},
        })
        return asyncio.run(api.core.download_delivery(request))

    def test_batch_mcp_delivers_one_revision_with_two_checked_cell_changes(self):
        second = {**self._operation(), "cell": self.table["cells"][0]["locator"],
                  "text": "두 번째 수정"}
        result = asyncio.run(api.core.mcp.call_tool("edit_preserved_table_batch_and_deliver", {
            "document_id": self.document_id, "expected_revision": 1,
            "operations": [self._operation(), second],
        }))
        self.assertFalse(result.is_error)
        receipt = result.structured_content
        self.assertEqual(receipt["revision"], 2)
        self.assertEqual(receipt["preserved_edit"]["operation_count"], 2)
        self.assertEqual(self.store.load_revision(self.document_id, 1)["bytes"], self.initial_bytes)
        self.assertEqual(self.store.load_current(self.document_id)["revision"], 2)
        self.assertIsNone(self.store.load_revision(self.document_id, 3))
        downloaded = self.download(result)
        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(downloaded.body, self.store.load_revision(self.document_id, 2)["bytes"])
        self.assertEqual(hashlib.sha256(downloaded.body).hexdigest(), receipt["sha256"])
        self.path.write_bytes(downloaded.body)
        cells = build_advanced_table_map(self.path)["tables"][0]["cells"]
        self.assertEqual([c["text"] for c in cells[:2]], ["두 번째 수정", "New verified value"])
        self.assertEqual([row["script"] for row in build_equation_map(self.path)["equations"]],
                         ["a + b"])

    def test_previewed_plan_matches_commit_and_rejects_edits_to_the_plan(self):
        operation = self._operation()
        preview = asyncio.run(api.core.mcp.call_tool("preview_preserved_table_batch", {
            "document_id": self.document_id, "expected_revision": 1, "operations": [operation],
        }))
        self.assertFalse(preview.is_error)
        pending = preview.structured_content
        self.assertEqual(pending["transaction"], "PREVIEW_ONLY")
        self.assertEqual(pending["changes"][0]["before"], "Editable target")
        self.assertEqual(pending["changes"][0]["after"], operation["text"])
        self.assert_original_revision()

        plan = pending["plan_sha256"]
        with self.assertRaisesRegex(ValueError, "PREVIEW_PLAN_MISMATCH"):
            api.edit_preserved_table_batch_and_deliver(
                self.document_id, 1, [{**operation, "text": "Different from preview"}],
                expected_plan_sha256=plan,
            )
        self.assert_original_revision()

        with self.assertRaisesRegex(ValueError, "PREVIEW_CANDIDATE_MISMATCH"):
            api.edit_preserved_table_batch_and_deliver(
                self.document_id, 1, [operation], expected_plan_sha256=plan,
                expected_candidate_sha256="0" * 64,
            )
        self.assert_original_revision()

        result = api.edit_preserved_table_batch_and_deliver(
            self.document_id, 1, [operation], expected_plan_sha256=plan,
            expected_candidate_sha256=pending["candidate_sha256"],
        )
        self.assertFalse(result.is_error)
        self.assertEqual(result.structured_content["plan_sha256"], plan)
        self.assertEqual(hashlib.sha256(self.download(result).body).hexdigest(),
                         pending["candidate_sha256"])
        self.assertEqual(result.structured_content["revision"], 2)
        with self.assertRaisesRegex(ValueError, "Stale revision"):
            api.edit_preserved_table_batch_and_deliver(
                self.document_id, 1, [operation], expected_plan_sha256=plan,
            )

    def test_layout_preview_is_opt_in_and_does_not_change_plan_or_revision(self):
        arguments = {"document_id": self.document_id, "expected_revision": 1,
                     "operations": [self._operation()]}
        with patch(
            "hwpx_mcp.custody.p427_structured_edit_preservation.preview_rhwp_layout",
            return_value={"status": "UNAVAILABLE", "reason": "RHWP_BINARY_NOT_INSTALLED"},
        ) as render:
            regular = asyncio.run(api.core.mcp.call_tool("preview_preserved_table_batch", arguments))
            self.assertNotIn("layout_preview", regular.structured_content)
            render.assert_not_called()
            rendered = asyncio.run(api.core.mcp.call_tool(
                "preview_preserved_table_batch",
                {**arguments, "layout_preview_pages": 1, "layout_preview_start_page": 3},
            ))
            render.assert_called_once()
            self.assertEqual(render.call_args.kwargs, {"max_pages": 1, "start_page": 3})
        self.assertEqual(rendered.structured_content["layout_preview"]["status"], "UNAVAILABLE")
        self.assertEqual(rendered.structured_content["plan_sha256"], regular.structured_content["plan_sha256"])
        self.assert_original_revision()

    def test_foreign_principal_cannot_preview_table_batch(self):
        with patch.object(api.core, "_caller_subject", return_value="foreign-subject"):
            with self.assertRaisesRegex(PermissionError, "not owned"):
                api.preview_preserved_table_batch(self.document_id, 1, [self._operation()])
        self.assert_original_revision()

    def test_host_phrase_preview_and_download_preserve_same_phrase_inside_child(self):
        with HwpxDocument.new() as doc:
            host = doc.add_table(1, 1)
            host.set_cell_text(0, 0, "동일한 설명")
            child = host.cell(0, 0).paragraphs[0].add_table(1, 1)
            child.set_cell_text(0, 0, "동일한 설명")
            child.cell(0, 0).paragraphs[0].add_equation("x + y")
            doc.save_to_path(str(self.path))
        self.seed_saved_document()
        host = build_advanced_table_map(self.path)["tables"][0]
        operation = {
            "op": "replace_cell_phrase", "table": host["locator"],
            "cell": host["cells"][0]["locator"], "paragraph_index": 0,
            "old_text": "동일한 설명", "new_text": "바깥 셀만 교정",
        }
        arguments = {
            "document_id": self.document_id, "expected_revision": 1,
            "operations": [operation],
        }
        preview = asyncio.run(api.core.mcp.call_tool("preview_preserved_table_batch", arguments))
        self.assertFalse(preview.is_error)
        planned = preview.structured_content
        self.assertEqual(planned["changes"][0]["after"], "바깥 셀만 교정")
        self.assert_original_revision()

        result = asyncio.run(api.core.mcp.call_tool(
            "edit_preserved_table_batch_and_deliver",
            {**arguments, "expected_plan_sha256": planned["plan_sha256"]},
        ))
        self.assertFalse(result.is_error)
        response = self.download(result)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.body, self.store.load_revision(self.document_id, 2)["bytes"])
        self.path.write_bytes(response.body)
        host, child = build_advanced_table_map(self.path)["tables"]
        self.assertEqual(host["cells"][0]["text"], "바깥 셀만 교정")
        self.assertEqual(child["cells"][0]["text"], "동일한 설명")
        self.assertEqual([item["script"] for item in build_equation_map(self.path)["equations"]],
                         ["x + y"])

    def test_late_batch_failure_creates_no_durable_revision(self):
        invalid_second = {
            "op": "replace_cell_phrase", "table": self.table["locator"],
            "cell": self.table["cells"][0]["locator"], "paragraph_index": 0,
            "old_text": "absent phrase", "new_text": "replacement",
        }
        with self.assertRaisesRegex(ValueError, "P427_BATCH_OPERATION_FAILED:1"):
            api.edit_preserved_table_batch_and_deliver(
                self.document_id, 1, [self._operation(), invalid_second],
            )
        self.assert_original_revision()

    def test_delivery_downloads_committed_revision_even_after_next_edit(self):
        export_revision = api.export_revision

        def advance_before_export(core, document_id, ttl, revision):
            self.assertEqual(revision, 2)
            api.apply_preserved_table_edit(document_id, 2, {
                **self._operation(), "text": "A newer revision",
            })
            return export_revision(core, document_id, ttl, revision)

        with patch.object(api, "export_revision", side_effect=advance_before_export):
            result = asyncio.run(api.core.mcp.call_tool("edit_preserved_table_and_deliver", {
                "document_id": self.document_id, "expected_revision": 1,
                "operation": self._operation(),
            }))

        self.assertFalse(result.is_error)
        receipt = result.structured_content
        self.assertEqual(receipt["revision"], 2)
        self.assertEqual(self.store.load_current(self.document_id)["revision"], 3)
        downloaded = self.download(result)
        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(downloaded.body, self.store.load_revision(self.document_id, 2)["bytes"])
        self.assertEqual(hashlib.sha256(downloaded.body).hexdigest(), receipt["sha256"])
        self.assertNotEqual(downloaded.body, self.store.load_current(self.document_id)["bytes"])
        self.path.write_bytes(downloaded.body)
        self.assertEqual([item["script"] for item in build_equation_map(self.path)["equations"]],
                         ["a + b"])

    def test_delivery_failure_renews_only_the_link_for_committed_revision(self):
        with patch.object(api, "export_revision", side_effect=RuntimeError("TEST_DELIVERY_UNAVAILABLE")):
            result = api.edit_preserved_table_and_deliver(self.document_id, 1, self._operation())

        self.assertTrue(result.is_error)
        receipt = result.structured_content
        self.assertEqual(receipt["delivery_status"], "RETRY_DELIVERY_ONLY")
        self.assertEqual(receipt["transaction"], "COMMITTED")
        self.assertEqual(receipt["revision"], 2)
        retry = api.deliver_document(self.document_id, revision=2)
        self.assertFalse(retry.is_error)
        self.assertEqual(retry.structured_content["sha256"], receipt["sha256"])
        self.assertIsNone(self.store.load_revision(self.document_id, 3))

    def test_mismatched_export_receipt_does_not_publish_a_download(self):
        export_revision = api.export_revision

        def mismatched_digest(*args):
            return {**export_revision(*args), "sha256": "0" * 64}

        with patch.object(api, "export_revision", side_effect=mismatched_digest):
            result = api.edit_preserved_table_and_deliver(self.document_id, 1, self._operation())

        self.assertTrue(result.is_error)
        receipt = result.structured_content
        self.assertEqual(receipt["delivery_status"], "RETRY_DELIVERY_ONLY")
        self.assertEqual(receipt["revision"], 2)
        self.assertNotIn("download_url", receipt)
        self.assertFalse(any(item.type == "resource_link" for item in result.content))
        retry = api.deliver_document(self.document_id, revision=2)
        self.assertEqual(hashlib.sha256(self.download(retry).body).hexdigest(), receipt["sha256"])
        self.assertIsNone(self.store.load_revision(self.document_id, 3))

    def assert_original_revision(self):
        row = self.store.load_current(self.document_id)
        self.assertEqual(row["revision"], 1)
        self.assertEqual(row["bytes"], self.initial_bytes)
        self.assertIsNone(self.store.load_revision(self.document_id, 2))

    def test_stale_revision_and_invalid_operation_leave_source_intact(self):
        with self.assertRaisesRegex(ValueError, "Stale revision"):
            api.apply_preserved_table_edit(self.document_id, 0, self._operation())
        with self.assertRaisesRegex(ValueError, "R3_EDIT_OPERATION_NOT_ADMITTED"):
            api.apply_preserved_table_edit(
                self.document_id, 1,
                {"op": "delete_table", "table": self.table["locator"]},
            )
        self.assert_original_revision()

    def test_real_owner_identity_check_blocks_foreign_caller(self):
        with patch.object(api.core, "_caller_subject", return_value="foreign-subject"):
            with self.assertRaisesRegex(PermissionError, "not owned"):
                api.apply_preserved_table_edit(self.document_id, 1, self._operation())
        self.assert_original_revision()

    def test_concurrent_edit_candidates_commit_only_the_winning_validated_bytes(self):
        rendezvous = Barrier(2)
        put_revision = self.store.put_revision

        def commit_together(**candidate):
            rendezvous.wait(timeout=20)
            return put_revision(**candidate)

        def attempt(text):
            operation = {**self._operation(), "text": text}
            try:
                return text, api.apply_preserved_table_edit(self.document_id, 1, operation)
            except RuntimeError as exc:
                return text, exc

        with patch.object(self.store, "put_revision", side_effect=commit_together):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(attempt, ["Concurrent A", "Concurrent B"]))

        winners = [(text, result) for text, result in results if isinstance(result, dict)]
        failures = [result for _, result in results if isinstance(result, RuntimeError)]
        self.assertEqual(len(winners), 1)
        self.assertEqual(len(failures), 1)
        self.assertRegex(str(failures[0]), "CAS conflict")
        text, receipt = winners[0]
        self.assertEqual(receipt["sha256"], self.digest())
        self.assertEqual(self.store.load_revision(self.document_id, 1)["bytes"], self.initial_bytes)
        self.assertIsNone(self.store.load_revision(self.document_id, 3))
        cells = build_advanced_table_map(self.path)["tables"][0]["cells"]
        self.assertEqual(next(c["text"] for c in cells if c["locator"] == self._operation()["cell"]),
                         text)

    def test_active_lease_is_required_and_can_authorize_the_commit(self):
        token = "p427-acceptance-lease-token"
        self.store.acquire_lease(
            self.document_id, holder_id=self.owner, expected_revision=1,
            lease_token=token, ttl_seconds=60,
        )
        with self.assertRaisesRegex(RuntimeError, "lease required"):
            api.apply_preserved_table_edit(self.document_id, 1, self._operation())
        self.assert_original_revision()
        result = api.apply_preserved_table_edit(self.document_id, 1, self._operation(), token)
        self.assertEqual(result["revision_after"], 2)
        self.assertEqual(result["sha256"], self.digest())

    def test_package_validator_failure_refuses_durable_commit(self):
        with patch.object(api.core, "validate_hwpx_package",
                          side_effect=ValueError("TEST_PACKAGE_REJECTED")):
            with self.assertRaisesRegex(ValueError, "TEST_PACKAGE_REJECTED"):
                api.apply_preserved_table_edit(self.document_id, 1, self._operation())
        self.assert_original_revision()

    def test_digest_collection_failure_refuses_durable_commit(self):
        with patch.object(api, "build_document_map", side_effect=RuntimeError("TEST_MAP_FAILED")):
            with self.assertRaisesRegex(RuntimeError, "TEST_MAP_FAILED"):
                api.apply_preserved_table_edit(self.document_id, 1, self._operation())
        self.assert_original_revision()


if __name__ == "__main__":
    unittest.main()
