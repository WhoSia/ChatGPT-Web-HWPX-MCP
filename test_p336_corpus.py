from __future__ import annotations
import tempfile
import unittest
import zipfile
from pathlib import Path

from p336_corpus import (
    blind_source_stem,
    build_native_style_census,
    canonical_pair_key,
    derive_engineering_priorities,
    inspect_native_style,
    source_stratified_split,
    validate_blind_ledger,
)


HEADER = b"""<?xml version="1.0" encoding="UTF-8"?>
<root>
  <fontface lang="HANGUL"><font id="0" face="UnitTestFont"/></fontface>
  <charPr id="0" height="1200"><fontRef hangul="0"/><spacing hangul="0"/></charPr>
  <charPr id="1" height="1500"><fontRef hangul="0"/><spacing hangul="-5"/><bold/></charPr>
  <paraPr id="0"><align horizontal="JUSTIFY"/><heading type="NONE" level="0"/></paraPr>
</root>"""
SECTION = b"""<?xml version="1.0" encoding="UTF-8"?>
<root>
  <p paraPrIDRef="0"><run charPrIDRef="0"><t>Body text for census.</t></run></p>
  <tbl><tc><p paraPrIDRef="0"><run charPrIDRef="1"><t>Table cell</t></run></p></tc></tbl>
</root>"""


def make_hwpx(path: Path, *, opaque=False):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("Contents/header.xml", b"OPAQUE" if opaque else HEADER)
        z.writestr("Contents/section0.xml", SECTION)


class P336CorpusTests(unittest.TestCase):
    def test_blind_id_is_stable_and_pairs_share_key(self):
        hwpx = canonical_pair_key("(보도자료)2024년+교육부+주요정책+추진계획+발표.hwpx")
        pdf = canonical_pair_key("(보도자료)2024년+교육부+주요정책+추진계획+발표.pdf")
        self.assertEqual(hwpx, pdf)
        self.assertEqual(blind_source_stem(hwpx), "gUveGpX7R07d")
        self.assertEqual(blind_source_stem("2026학년도_돌봄교실_운영_계획"), "anUUE6Qq3Brh")

    def test_ledger_and_split_keep_source_groups_indivisible(self):
        rows = [
            {"blind_id": "AAAAAAAAAAAA", "blind_filename": "AAAAAAAAAAAA.hwpx", "source_group": "g1", "split": "DISCOVERY"},
            {"blind_id": "BBBBBBBBBBBB", "blind_filename": "BBBBBBBBBBBB.hwpx", "source_group": "g1", "split": "DISCOVERY"},
            {"blind_id": "CCCCCCCCCCCC", "blind_filename": "CCCCCCCCCCCC.hwpx", "source_group": "g2", "split": "HOLDOUT"},
            {"blind_id": "DDDDDDDDDDDD", "blind_filename": "DDDDDDDDDDDD.hwpx", "source_group": "g3", "split": "CALIBRATION"},
        ]
        self.assertEqual(validate_blind_ledger(rows)["sources"], 4)
        out = source_stratified_split([{"source_group": r["source_group"], "id": i} for i, r in enumerate(rows)])
        grouped = {}
        for row in out["assignments"]:
            grouped.setdefault(row["source_group"], set()).add(row["split"])
        self.assertTrue(all(len(v) == 1 for v in grouped.values()))

    def test_native_inspection_and_census_are_descriptive_not_normative(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "AAAAAAAAAAAA.hwpx"
            make_hwpx(path)
            row = inspect_native_style(path, blind_id="AAAAAAAAAAAA")
        self.assertEqual(row["status"], "PASS")
        self.assertGreater(row["tables"], 0)
        self.assertEqual(row["dominant_fonts"][0]["value"], "UnitTestFont")
        census = build_native_style_census([row])
        self.assertEqual(census["authority"], "EMPIRICAL_CONVENTION_CENSUS_NOT_AESTHETIC_NORM")
        priorities = derive_engineering_priorities(census)
        table = next(x for x in priorities["priorities"] if x["priority"] == "TABLE_AUTHORING_AND_LAYOUT_ROBUSTNESS")
        self.assertIn("not", table["non_inference"].lower())
        self.assertEqual(priorities["design_authority_ladder"][-1], "EXPLICIT_HUMAN_DESIGN_TARGET")

    def test_opaque_xml_payload_is_compatibility_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "BBBBBBBBBBBB.hwpx"
            make_hwpx(path, opaque=True)
            row = inspect_native_style(path, blind_id="BBBBBBBBBBBB")
        self.assertEqual(row["status"], "PARSER_HOLD_OPAQUE_XML_PAYLOAD")


if __name__ == "__main__":
    unittest.main()
