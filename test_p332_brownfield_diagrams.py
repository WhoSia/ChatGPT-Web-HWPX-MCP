from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from hwpx import HwpxDocument

from p2_document import build_document_map
from p328_high_level_diagrams import _insert_labeled_node, _insert_pointer_line
from p327_diagram_composition import _position_xy, _resolve_top, _size
from p329_diagram_lifecycle import apply_diagram_lifecycle_atomic, build_diagram_lifecycle_map
from p332_brownfield_diagrams import (
    apply_legacy_diagram_refactor_atomic,
    brownfield_diagram_contract,
    build_brownfield_diagram_map,
    plan_diagram_adoption,
    plan_legacy_diagram_refactor,
    promote_diagram_candidate_atomic,
)


class BrownfieldDiagramTests(unittest.TestCase):
    def _base(self, directory: Path) -> tuple[Path, str]:
        path = directory / "p332.hwpx"
        doc = HwpxDocument.new()
        doc.add_paragraph("P3.32 anchor")
        doc.save_to_path(str(path))
        doc.close()
        mapped = build_document_map(path)
        anchor = next(p["locator"] for p in mapped["paragraphs"] if p.get("text") == "P3.32 anchor")
        return path, anchor

    def _legacy_pair(self, path: Path, anchor: str, *, occupied_name: bool = False) -> tuple[str, str]:
        left = _insert_labeled_node(path, {
            "anchor": anchor,
            "node_type": "process",
            "text": "Legacy A",
            "horizontal_offset": 1000,
            "vertical_offset": 1000,
            "name": "legacy-meta" if occupied_name else "",
        })["created_node"]
        right = _insert_labeled_node(path, {
            "anchor": anchor,
            "node_type": "terminator",
            "text": "Legacy B",
            "horizontal_offset": 12000,
            "vertical_offset": 1000,
        })["created_node"]
        a = _resolve_top(path, left)
        b = _resolve_top(path, right)
        ax, ay = _position_xy(a)
        bx, by = _position_xy(b)
        aw, ah = _size(a)
        bw, bh = _size(b)
        _insert_pointer_line(
            path,
            anchor=anchor,
            start=(ax + aw // 2, ay + ah // 2),
            end=(bx + bw // 2, by + bh // 2),
            line_color="#555555",
            line_width=200,
        )
        return left, right

    def test_recognizes_connected_unmanaged_native_diagram_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = self._base(Path(tmp))
            self._legacy_pair(path, anchor)
            before = path.read_bytes()
            mapped = build_brownfield_diagram_map(path)
            self.assertEqual(mapped["candidate_count"], 1)
            self.assertEqual(mapped["promotable_candidate_count"], 1)
            self.assertEqual(mapped["candidates"][0]["node_count"], 2)
            self.assertEqual(mapped["candidates"][0]["edge_count"], 1)
            self.assertEqual(path.read_bytes(), before)

    def test_occupied_name_carrier_is_recognized_but_held(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = self._base(Path(tmp))
            self._legacy_pair(path, anchor, occupied_name=True)
            candidate = build_brownfield_diagram_map(path)["candidates"][0]
            self.assertFalse(candidate["promotable"])
            self.assertIn("NAME_CARRIER_OCCUPIED", candidate["hold_reasons"])
            with self.assertRaisesRegex(ValueError, "not promotable"):
                plan_diagram_adoption(path, candidate["candidate_id"], "legacy")

    def test_plan_and_promotion_preserve_native_object_identity_and_relations(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = self._base(Path(tmp))
            left, right = self._legacy_pair(path, anchor)
            candidate = build_brownfield_diagram_map(path)["candidates"][0]
            plan = plan_diagram_adoption(
                path,
                candidate["candidate_id"],
                "adopted",
                node_bindings={
                    left: {"node_id": "input", "node_type": "process"},
                    right: {"node_id": "end", "node_type": "terminator"},
                },
            )
            receipt = promote_diagram_candidate_atomic(
                path,
                plan,
                expected_revision=1,
                current_revision=1,
            )
            self.assertTrue(receipt["source_object_identity_preserved"])
            lifecycle = build_diagram_lifecycle_map(path)
            diagram = next(d for d in lifecycle["diagrams"] if d["diagram_id"] == "adopted")
            self.assertEqual(diagram["node_count"], 2)
            self.assertEqual(diagram["edge_count"], 1)
            self.assertEqual({n["locator"] for n in diagram["nodes"]}, {left, right})
            self.assertEqual([(e["source"], e["target"]) for e in diagram["edges"]], [("input", "end")])

    def test_stale_adoption_plan_fails_after_source_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = self._base(Path(tmp))
            left, _right = self._legacy_pair(path, anchor)
            candidate = build_brownfield_diagram_map(path)["candidates"][0]
            plan = plan_diagram_adoption(path, candidate["candidate_id"], "adopted")
            from p328_high_level_diagrams import _set_existing_shape_text
            _set_existing_shape_text(path, {"drawing": left, "text": "Changed"})
            with self.assertRaisesRegex(ValueError, "stale"):
                promote_diagram_candidate_atomic(
                    path,
                    plan,
                    expected_revision=2,
                    current_revision=2,
                )

    def test_mixed_managed_and_unmanaged_diagrams_do_not_cross_adopt(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = self._base(Path(tmp))
            apply_diagram_lifecycle_atomic(
                path,
                [{"op": "instantiate_template", "diagram_id": "managed", "anchor": anchor, "template": "linear_process"}],
                expected_revision=1,
                current_revision=1,
            )
            self._legacy_pair(path, anchor)
            mapped = build_brownfield_diagram_map(path)
            self.assertEqual(mapped["managed_diagram_count"], 1)
            self.assertEqual(mapped["candidate_count"], 1)
            managed_locators = {
                n["locator"]
                for d in build_diagram_lifecycle_map(path)["diagrams"]
                for n in d["nodes"]
            }
            candidate_locators = {n["locator"] for n in mapped["candidates"][0]["nodes"]}
            self.assertTrue(managed_locators.isdisjoint(candidate_locators))

    def test_post_promotion_refactor_preserves_relation_and_reingest_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path, anchor = self._base(root)
            self._legacy_pair(path, anchor)
            candidate = build_brownfield_diagram_map(path)["candidates"][0]
            adoption = plan_diagram_adoption(path, candidate["candidate_id"], "legacy")
            promote_diagram_candidate_atomic(path, adoption, expected_revision=1, current_revision=1)
            before = build_diagram_lifecycle_map(path)["diagrams"][0]["relation_sha256"]
            refactor = plan_legacy_diagram_refactor(
                path, "legacy", layout_policy="standard", theme="mono"
            )
            receipt = apply_legacy_diagram_refactor_atomic(
                path,
                refactor,
                expected_revision=2,
                current_revision=2,
            )
            self.assertTrue(receipt["relation_preserved"])
            self.assertEqual(receipt["relation_sha256"], before)
            copied = root / "reingested.hwpx"
            shutil.copyfile(path, copied)
            again = build_diagram_lifecycle_map(copied)
            self.assertEqual(again["diagram_count"], 1)
            self.assertEqual(again["diagrams"][0]["relation_sha256"], before)

    def test_adoption_plan_hash_rejects_binding_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = self._base(Path(tmp))
            self._legacy_pair(path, anchor)
            candidate = build_brownfield_diagram_map(path)["candidates"][0]
            plan = plan_diagram_adoption(path, candidate["candidate_id"], "adopted")
            plan["bindings"][0]["node_id"] = "tampered"
            before = path.read_bytes()
            with self.assertRaisesRegex(ValueError, "plan hash mismatch"):
                promote_diagram_candidate_atomic(
                    path,
                    plan,
                    expected_revision=1,
                    current_revision=1,
                )
            self.assertEqual(path.read_bytes(), before)

    def test_refactor_plan_hash_rejects_operation_tamper_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = self._base(Path(tmp))
            self._legacy_pair(path, anchor)
            candidate = build_brownfield_diagram_map(path)["candidates"][0]
            adoption = plan_diagram_adoption(path, candidate["candidate_id"], "legacy")
            promote_diagram_candidate_atomic(path, adoption, expected_revision=1, current_revision=1)
            refactor = plan_legacy_diagram_refactor(
                path, "legacy", layout_policy="standard", theme="mono"
            )
            refactor["operations"][-1]["theme"] = "classic"
            before = path.read_bytes()
            with self.assertRaisesRegex(ValueError, "plan hash mismatch"):
                apply_legacy_diagram_refactor_atomic(
                    path,
                    refactor,
                    expected_revision=2,
                    current_revision=2,
                )
            self.assertEqual(path.read_bytes(), before)

    def test_contract_keeps_visual_and_semantic_inference_gates_closed(self):
        contract = brownfield_diagram_contract()
        self.assertEqual(contract["phase"], "P3.32")
        self.assertIn("pixel_visual_recognition", contract["deferred_operations"])
        self.assertIn("semantic_auto_repair", contract["deferred_operations"])


if __name__ == "__main__":
    unittest.main()
