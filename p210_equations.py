from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Callable

from hwpx import HwpxDocument
from hwpx.equation import estimate_equation_size, latex_to_eqedit
from hwpx.oxml.paragraph import HwpxOxmlParagraph

from p2_document import build_document_map
from p28_tables import _save_document

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
MAX_LATEX_CHARS = 8192


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _paragraphs(section) -> list:
    return [node for node in section.element.iter() if _local(node.tag) == "p"]


def _paragraph_lookup(path: Path) -> dict[tuple[int, int], dict]:
    mapped = build_document_map(path)
    return {
        (int(p["section_index"]), int(p["paragraph_index"])): p
        for p in mapped["paragraphs"]
    }


def _equation_locator(section_index: int, equation_index: int, element) -> tuple[str, str]:
    intrinsic = element.get("id") or element.get("instid")
    if intrinsic:
        seed = f"section:{section_index}\0equation-id\0{intrinsic}"
        stability = "intrinsic-id"
    else:
        seed = f"section:{section_index}\0equation-ordinal\0{equation_index}"
        stability = "revision-bound-ordinal"
    return "eq_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20], stability


def _equations(document) -> list[dict]:
    result: list[dict] = []
    global_index = 0
    for section_index, section in enumerate(document._root.sections):
        paras = _paragraphs(section)
        para_ord = {id(node): index for index, node in enumerate(paras)}
        for node in section.element.iter():
            if _local(node.tag) != "equation":
                continue
            owner = node.getparent() if hasattr(node, "getparent") else None
            while owner is not None and _local(owner.tag) != "p":
                owner = owner.getparent() if hasattr(owner, "getparent") else None
            paragraph_index = para_ord.get(id(owner), -1)
            script_el = node.find(f"{HP}script")
            sz = node.find(f"{HP}sz")
            pos = node.find(f"{HP}pos")
            locator, stability = _equation_locator(section_index, global_index, node)
            script = "" if script_el is None else (script_el.text or "")
            result.append({
                "locator": locator,
                "address_stability": stability,
                "intrinsic_id": node.get("id") or node.get("instid"),
                "equation_index": global_index,
                "section_index": section_index,
                "paragraph_index": paragraph_index,
                "element": node,
                "script": script,
                "script_sha256": hashlib.sha256(script.encode("utf-8")).hexdigest(),
                "width": None if sz is None else int(sz.get("width", "0") or 0),
                "height": None if sz is None else int(sz.get("height", "0") or 0),
                "size_attributes": None if sz is None else dict(sz.attrib),
                "position": None if pos is None else dict(pos.attrib),
                "base_unit": int(node.get("baseUnit", "0") or 0),
                "base_line": int(node.get("baseLine", "0") or 0),
                "font": node.get("font"),
                "version": node.get("version"),
                "text_color": node.get("textColor"),
                "line_mode": node.get("lineMode"),
            })
            global_index += 1
    return result


def build_equation_map(path: Path) -> dict:
    document = HwpxDocument.open(str(path))
    try:
        paragraph_map = _paragraph_lookup(path)
        equations: list[dict] = []
        topology_seed: list[dict] = []
        geometry_seed: list[dict] = []
        script_seed: list[dict] = []
        for eq in _equations(document):
            payload = {k: v for k, v in eq.items() if k != "element"}
            paragraph = paragraph_map.get((eq["section_index"], eq["paragraph_index"]))
            payload["paragraph_locator"] = None if paragraph is None else paragraph["locator"]
            equations.append(payload)
            topology_seed.append({
                "locator": payload["locator"],
                "section_index": payload["section_index"],
                "paragraph_locator": payload["paragraph_locator"],
                "intrinsic_id": payload["intrinsic_id"],
            })
            geometry_seed.append({
                "locator": payload["locator"],
                "width": payload["width"],
                "height": payload["height"],
                "size_attributes": payload["size_attributes"],
                "position": payload["position"],
                "base_unit": payload["base_unit"],
                "base_line": payload["base_line"],
            })
            script_seed.append({
                "locator": payload["locator"],
                "script_sha256": payload["script_sha256"],
            })

        def digest(value: object) -> str:
            return hashlib.sha256(
                json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()

        return {
            "equations": equations,
            "equation_count": len(equations),
            "equation_structure_sha256": digest(topology_seed),
            "equation_geometry_sha256": digest(geometry_seed),
            "equation_script_custody_sha256": digest(script_seed),
        }
    finally:
        document.close()


def _resolve_equation(mapped: dict, locator: object) -> dict:
    value = str(locator or "")
    target = next((item for item in mapped["equations"] if item["locator"] == value), None)
    if target is None:
        raise ValueError(f"Unknown equation locator: {value}")
    return target


def _resolve_paragraph(document, path: Path, locator: object):
    mapped = build_document_map(path)
    target = next((p for p in mapped["paragraphs"] if p["locator"] == str(locator or "")), None)
    if target is None:
        raise ValueError(f"Unknown paragraph locator: {locator}")
    section = document._root.sections[int(target["section_index"])]
    nodes = _paragraphs(section)
    index = int(target["paragraph_index"])
    if index < 0 or index >= len(nodes):
        raise ValueError("paragraph locator no longer resolves")
    return HwpxOxmlParagraph(nodes[index], section), target


def _verified_script(op: dict) -> tuple[str, str]:
    if "eqedit_script" in op:
        raise ValueError(
            "raw EqEdit authoring evidence gate is closed; use verified LaTeX conversion"
        )
    latex = op.get("latex")
    if not isinstance(latex, str) or not latex.strip():
        raise ValueError("latex must be a non-empty string")
    if len(latex) > MAX_LATEX_CHARS:
        raise ValueError("latex input exceeds P2.10 custody bound")
    script = latex_to_eqedit(latex)
    return latex, script


def _set_equation_size(element, width: int, height: int) -> None:
    if width <= 0 or height <= 0 or width > 10_000_000 or height > 10_000_000:
        raise ValueError("equation width/height are outside admitted HWPUNIT bounds")
    sz = element.find(f"{HP}sz")
    if sz is None:
        raise ValueError("equation has no mutable hp:sz geometry")
    sz.set("width", str(width))
    sz.set("height", str(height))


def _remove_equation(document, target: dict) -> None:
    current = _equations(document)[int(target["equation_index"])]
    element = current["element"]
    parent = element.getparent() if hasattr(element, "getparent") else None
    if parent is None:
        raise ValueError("equation has no mutable run parent")
    parent.remove(element)
    run_parent = parent.getparent() if hasattr(parent, "getparent") else None
    if len(parent) == 0 and run_parent is not None and _local(parent.tag) == "run":
        run_parent.remove(parent)
    document._root.sections[int(current["section_index"])].mark_dirty()


def _apply_one(candidate: Path, op: dict) -> dict:
    name = op.get("op")
    before = build_equation_map(candidate)
    document = HwpxDocument.open(str(candidate))
    try:
        if name == "insert_equation":
            _latex, script = _verified_script(op)
            paragraph, paragraph_info = _resolve_paragraph(document, candidate, op.get("paragraph"))
            base_unit = int(op.get("base_unit", 1100))
            if base_unit <= 0 or base_unit > 100000:
                raise ValueError("base_unit is outside admitted bounds")
            size = None
            if "width" in op or "height" in op:
                if "width" not in op or "height" not in op:
                    raise ValueError("explicit equation geometry requires both width and height")
                size = (int(op["width"]), int(op["height"]))
                if size[0] <= 0 or size[1] <= 0:
                    raise ValueError("equation width/height must be positive")
            document.shapes.add_equation(
                script,
                paragraph=paragraph,
                base_unit=base_unit,
                size=size,
            )
            _save_document(document, candidate, candidate)
            after = build_equation_map(candidate)
            old = {item["locator"] for item in before["equations"]}
            created = [item for item in after["equations"] if item["locator"] not in old]
            if len(created) != 1:
                raise ValueError("insert_equation did not yield one uniquely identifiable equation")
            return {
                "op": name,
                "created_equation": created[0]["locator"],
                "paragraph": paragraph_info["locator"],
                "script_sha256": created[0]["script_sha256"],
            }

        target = _resolve_equation(before, op.get("equation"))
        current = _equations(document)[int(target["equation_index"])]

        if name == "replace_equation":
            _latex, script = _verified_script(op)
            script_el = current["element"].find(f"{HP}script")
            if script_el is None:
                raise ValueError("equation has no hp:script child")
            script_el.text = script
            base_unit = int(op.get("base_unit", current["base_unit"] or 1100))
            if base_unit <= 0 or base_unit > 100000:
                raise ValueError("base_unit is outside admitted bounds")
            current["element"].set("baseUnit", str(base_unit))
            if bool(op.get("preserve_size", False)):
                width, height = int(current["width"]), int(current["height"])
            else:
                width, height = estimate_equation_size(script, base_unit=base_unit)
            _set_equation_size(current["element"], width, height)
            document._root.sections[int(current["section_index"])].mark_dirty()
            _save_document(document, candidate, candidate)
            return {
                "op": name,
                "equation": target["locator"],
                "script_sha256": hashlib.sha256(script.encode("utf-8")).hexdigest(),
                "width": width,
                "height": height,
            }

        if name == "remove_equation":
            _remove_equation(document, target)
            _save_document(document, candidate, candidate)
            return {"op": name, "removed_equation": target["locator"]}

        if name == "resize_equation":
            width, height = int(op["width"]), int(op["height"])
            _set_equation_size(current["element"], width, height)
            document._root.sections[int(current["section_index"])].mark_dirty()
            _save_document(document, candidate, candidate)
            return {
                "op": name,
                "equation": target["locator"],
                "width": width,
                "height": height,
            }

        raise ValueError(f"Unsupported equation operation: {name}")
    finally:
        document.close()


def _rebinding(before: dict, after: dict) -> dict:
    b = {item["locator"] for item in before["equations"]}
    a = {item["locator"] for item in after["equations"]}
    return {
        "created_equations": sorted(a - b),
        "deleted_equations": sorted(b - a),
        "stable_equations": sorted(a & b),
        "reacquire_required": bool(a != b),
    }


def apply_equation_edits_atomic(
    path: Path,
    operations: list[dict],
    *,
    expected_revision: int,
    current_revision: int,
    validator: Callable[[Path], dict] | None = None,
) -> dict:
    if expected_revision != current_revision:
        raise ValueError(f"Stale revision: expected {expected_revision}, current {current_revision}")
    if not operations or len(operations) > 20:
        raise ValueError("Equation transaction requires 1..20 operations")
    if not all(isinstance(op, dict) for op in operations):
        raise ValueError("Each equation operation must be an object")

    before = build_equation_map(path)
    fd, tmp_name = tempfile.mkstemp(prefix=path.stem + ".p210-", suffix=".hwpx", dir=str(path.parent))
    os.close(fd)
    candidate = Path(tmp_name)
    candidate.write_bytes(path.read_bytes())
    receipts: list[dict] = []
    validation = None

    try:
        for op in operations:
            receipts.append(_apply_one(candidate, op))
        after = build_equation_map(candidate)
        if validator is not None:
            validation = validator(candidate)
        os.replace(candidate, path)
    except Exception:
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass
        raise

    result = {
        "before": {
            "equation_count": before["equation_count"],
            "equation_structure_sha256": before["equation_structure_sha256"],
            "equation_geometry_sha256": before["equation_geometry_sha256"],
            "equation_script_custody_sha256": before["equation_script_custody_sha256"],
        },
        "after": {
            "equation_count": after["equation_count"],
            "equation_structure_sha256": after["equation_structure_sha256"],
            "equation_geometry_sha256": after["equation_geometry_sha256"],
            "equation_script_custody_sha256": after["equation_script_custody_sha256"],
        },
        "equation_structure_changed": before["equation_structure_sha256"] != after["equation_structure_sha256"],
        "equation_geometry_changed": before["equation_geometry_sha256"] != after["equation_geometry_sha256"],
        "equation_script_custody_changed": before["equation_script_custody_sha256"] != after["equation_script_custody_sha256"],
        "equation_rebinding": _rebinding(before, after),
        "operation_count": len(operations),
        "receipts": receipts,
    }
    if validation is not None:
        result["validation"] = validation
    return result
