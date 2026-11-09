"""Batch Hancom local workflow; synthetic PDFs, no Windows COM needed."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = str(Path(__file__).resolve().parents[1] / "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from p424_batch_native_pdf import convert_batch, _directory_name


PDF = b"%PDF-1.7\n" + b"synthetic" * 20 + b"\n%%EOF\n"


class BatchNativePdfTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.inputs = self.root / "in"
        self.outputs = self.root / "out"
        self.inputs.mkdir()
        self.outputs.mkdir()
        self.calls = []

    def source(self, name, content=b"PKtest"):
        path = self.inputs / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def convert(self, src, out):
        self.calls.append(src.name)
        if src.stem == "broken":
            raise RuntimeError("synthetic conversion failure")
        pdf = out / (src.stem + ".native-hancom.pdf")
        pdf.write_bytes(PDF)
        result = {
            "schema": "p424.local-work.native-hancom-acceptance.v1",
            "source_hwpx_sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
            "native_pdf_file": pdf.name,
            "native_pdf_sha256": hashlib.sha256(PDF).hexdigest(),
            "native_pdf_bytes": len(PDF),
            "native_pdf_created": True,
            "visual_acceptance": "REQUIRES_HUMAN_PAGE_REVIEW",
        }
        (out / (src.stem + ".p424-acceptance.json")).write_text(
            json.dumps(result), encoding="utf-8"
        )
        return result

    def test_first_run_then_resume_without_reconversion(self):
        file = self.source("math.hwpx")
        first = convert_batch([file], self.outputs, conversion=self.convert)
        self.assertEqual(first["summary"]["CREATED_UNREVIEWED"], 1)
        second = convert_batch([file], self.outputs, conversion=self.convert)
        self.assertEqual(second["summary"]["REUSED_VERIFIED"], 1)
        self.assertEqual(self.calls, ["math.hwpx"])
        self.assertTrue(second["visual_review_required"])
        self.assertFalse(second["production_approved"])

    def test_modified_source_cannot_reuse_old_pdf(self):
        file = self.source("math.hwpx")
        convert_batch([file], self.outputs, conversion=self.convert)
        file.write_bytes(b"PKchanged")
        second = convert_batch([file], self.outputs, conversion=self.convert)
        self.assertEqual(second["summary"]["BLOCKED_EXISTING_ARTIFACTS"], 1)
        self.assertEqual(self.calls, ["math.hwpx"])

    def test_corrupted_pdf_is_not_treated_as_verified(self):
        file = self.source("math.hwpx")
        convert_batch([file], self.outputs, conversion=self.convert)
        pdf = self.outputs / _directory_name(file) / "math.native-hancom.pdf"
        pdf.write_bytes(b"%PDF-incorrect")
        again = convert_batch([file], self.outputs, conversion=self.convert)
        self.assertEqual(again["summary"]["BLOCKED_EXISTING_ARTIFACTS"], 1)

    def test_failures_do_not_prevent_other_documents(self):
        broken = self.source("broken.hwpx")
        valid = self.source("valid.hwpx")
        result = convert_batch([broken, valid], self.outputs, conversion=self.convert)
        self.assertEqual(result["summary"]["FAILED"], 1)
        self.assertEqual(result["summary"]["CREATED_UNREVIEWED"], 1)
        self.assertEqual(result["total_inputs"], 2)

    def test_deduplicate_inputs_and_recursive_discovery(self):
        first = self.source("one.hwpx")
        nested = self.source("sub/two.hwpx")
        result = convert_batch([self.inputs, first], self.outputs,
                               recursive=True, conversion=self.convert)
        self.assertEqual(result["total_inputs"], 2)
        self.assertEqual(result["summary"]["CREATED_UNREVIEWED"], 2)

    def test_output_tree_input_is_skipped(self):
        source = self.outputs / "generated.hwpx"
        source.write_bytes(b"PKsynthetic")
        result = convert_batch([source], self.outputs, conversion=self.convert)
        self.assertEqual(result["summary"]["SKIPPED_OUTPUT_TREE"], 1)
        self.assertEqual(self.calls, [])

    def test_same_filename_in_different_directories_isolated(self):
        a = self.source("x/a.hwpx", b"PK-1")
        b = self.source("y/a.hwpx", b"PK-2")
        result = convert_batch([a, b], self.outputs, conversion=self.convert)
        self.assertEqual(result["summary"]["CREATED_UNREVIEWED"], 2)
        self.assertNotEqual(_directory_name(a), _directory_name(b))


if __name__ == "__main__":
    unittest.main()
