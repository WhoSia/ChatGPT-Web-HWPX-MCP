"""P4.20: preserve executable document-domain APIs after package migration."""
from __future__ import annotations

import hashlib
import inspect
import tempfile
import unittest
import zipfile
from pathlib import Path

from hwpx_mcp.document.p317_page_geometry import (
    build_page_geometry_map,
    apply_page_geometry_edits_atomic,
)
from hwpx_mcp.document.p334r2_package_validation import validate_hwpx_package_light
from hwpx_mcp.orchestration.p344_autonomous_authoring import autonomous_authoring_contract


def _minimal_hwpx(path: Path) -> None:
    # Standalone structural fixture; no server, OAuth, network or render service.
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", b"application/hwp+zip", compress_type=zipfile.ZIP_STORED)
        for name in ("Contents/header.xml", "META-INF/container.xml"):
            archive.writestr(name, b"<root/>")
        archive.writestr(
            "Contents/section0.xml",
            b'<section><pagePr><margin left="100" right="200" top="300"/></pagePr></section>',
        )


class PackagedDocumentContracts(unittest.TestCase):
    def test_signatures_match_pre_move_exports(self):
        self.assertEqual(list(inspect.signature(validate_hwpx_package_light).parameters), ["path"])
        self.assertEqual(list(inspect.signature(build_page_geometry_map).parameters), ["path"])
        self.assertEqual(
            list(inspect.signature(apply_page_geometry_edits_atomic).parameters),
            ["path", "operations", "expected_revision", "current_revision", "validator"],
        )
        self.assertEqual(list(inspect.signature(autonomous_authoring_contract).parameters), [])

    def test_light_validator_remains_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "minimal.hwpx"
            _minimal_hwpx(path)
            result = validate_hwpx_package_light(path)
            self.assertTrue(result["valid"])
            self.assertEqual(result["zip_entries"], 4)
            self.assertEqual(result["parsed_xml_entries"], 3)

    def test_page_geometry_edit_is_atomic_and_revision_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "minimal.hwpx"
            _minimal_hwpx(path)
            before = build_page_geometry_map(path)
            initial = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(before["sections"][0]["margin"]["left"], "100")
            with self.assertRaises(ValueError):
                apply_page_geometry_edits_atomic(
                    path, [{"op": "set_page_margin", "left": 350}],
                    expected_revision=1, current_revision=2,
                )
            self.assertEqual(initial, hashlib.sha256(path.read_bytes()).hexdigest())
            edited = apply_page_geometry_edits_atomic(
                path, [{"op": "set_page_margin", "left": 350}],
                expected_revision=2, current_revision=2,
                validator=validate_hwpx_package_light,
            )
            self.assertTrue(edited["page_geometry_changed"])
            self.assertTrue(edited["validation"]["valid"])
            self.assertEqual(build_page_geometry_map(path)["sections"][0]["margin"]["left"], "350")

    def test_autonomous_authoring_contract_retains_phase(self):
        contract = autonomous_authoring_contract()
        self.assertEqual(contract["phase"], "P3.44")
        self.assertIn("PLAN", contract["pipeline"])
        self.assertIn("DELIVER", contract["pipeline"])


if __name__ == "__main__":
    unittest.main()
