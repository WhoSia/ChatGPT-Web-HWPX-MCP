"""Keep runtime, deployment, and attachment evidence tied to exact identities."""
import hashlib
import tempfile
import unittest
from pathlib import Path

from scripts.p429_check_attachment import assess_attachment
from scripts.p429_check_live_build import assess_render_deployment


class ReleaseReadbackTests(unittest.TestCase):
    def test_render_and_runtime_must_both_match(self):
        expected = "a" * 40
        old = "b" * 40
        current_health = {"status": "ok", "release_commit": expected}
        live = {"id": "dep-test", "status": "live", "commit": {"id": expected}}
        cases = (
            (current_health, live, "BUILD_MATCH"),
            (current_health, {**live, "status": "deactivated"}, "DEPLOY_NOT_LIVE"),
            (current_health, {**live, "commit": {"id": old}}, "DEPLOY_BUILD_MISMATCH"),
            ({**current_health, "release_commit": old}, live, "BUILD_MISMATCH"),
            ({"status": "down", "release_commit": expected}, live, "UNHEALTHY"),
        )
        for health, deployment, verdict in cases:
            with self.subTest(verdict=verdict):
                self.assertEqual(assess_render_deployment(expected, health, deployment)["verdict"], verdict)

    def test_replaced_attachment_cannot_pass_with_the_same_filename(self):
        original = b"committed document"
        receipt = {"revision": 2, "sha256": hashlib.sha256(original).hexdigest()}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "download.hwpx"
            path.write_bytes(original)
            self.assertEqual(assess_attachment(path, receipt)["verdict"], "ATTACHMENT_MATCH")
            path.write_bytes(b"different document")
            self.assertEqual(assess_attachment(path, receipt)["verdict"], "ATTACHMENT_MISMATCH")
