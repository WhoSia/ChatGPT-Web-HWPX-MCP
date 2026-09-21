from __future__ import annotations

import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable

from lxml import etree

from p2_document import build_document_map
from p39_textbox import inject_textbox

HP_URI = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HP = f"{{{HP_URI}}}"
SCHEMA = "chatgpt-web-hwpx-mcp/drawing-layer/p3.25/v1"
DRAWING_TAGS = {"pic", "rect", "ellipse", "line", "polygon", "arc", "container"}
RESIZABLE_KINDS = {"pic", "rect"}
WRAP_MODES = {
    "TOP_AND_BOTTOM", "SQUARE", "TIGHT", "THROUGH",
    "BEHIND_TEXT", "IN_FRONT_OF_TEXT",
}
DEFERRED_OPERATIONS = {
    "group_objects": (
        "EVIDENCE_GATE_CLOSED: container/group authoring requires measured child-transform "
        "and cross-object ownership custody; existing groups are read-only."
    ),
    "ungroup_objects": (
        "EVIDENCE_GATE_CLOSED: ungrouping is not admitted until child transforms can be "
        "rebased without geometry drift."
    ),
    "insert_generic_shape": (
        "EVIDENCE_GATE_CLOSED: generic add_shape can omit mandatory OWPML children; "
        "use admitted rectangle/textbox authoring or an evidence-backed dedicated helper."
    ),
}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def drawing_layer_contract() -> dict:
    return {
        "phase": "P3.25",
        "authority": "STRUCTURAL_DRAWING_LAYER_AUTHORITY_ONLY",
        "native_render_batch_status": "DEFERRED_BY_DESIGN",
        "ancestry": {
            "P2.9": "picture/media custody, floating anchor, resize and position primitives",
            "P3.9": "native rectangle-textbox promotion and HWPUNIT anchor/geometry receipts",
            "P3.25": "unified drawing-object map, layout/z-order/rotation/flip transactions and production authoring",
        },
        "inventoried_families": sorted(DRAWING_TAGS),
        "admitted_authoring": ["insert_textbox", "insert_rectangle"],
        "admitted_operations": [
            "insert_textbox",
            "insert_rectangle",
            "set_drawing_layout",
            "resize_drawing_object",
            "rotate_drawing_object",
            "flip_drawing_object",
            "remove_drawing_object",
        ],
        "resizable_families": sorted(RESIZABLE_KINDS),
        "deferred_operations": dict(DEFERRED_OPERATIONS),
    }


def _paragraph_map(path: Path) -> dict[tuple[str, int], dict]:
    mapped = build_document_map(path)
    return {
        (str(item["section"]), int(item["paragraph_index"])): item
        for item in mapped["paragraphs"]
    }


def _paragraphs(root) -> list:
    return [node for node in root.iter() if _local(node.tag) == "p"]


def _drawing_locator(section: str, index: int, node) -> tuple[str, str]:
    intrinsic = node.get("instid") or node.get("id")
    if intrinsic:
        seed = f"{section}\0drawing-id\0{intrinsic}"
        stability = "intrinsic-id"
    else:
        seed = f"{section}\0drawing-ordinal\0{index}"
        stability = "revision-bound-ordinal"
    return "d_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20], stability


def _text_payload(node) -> tuple[bool, list[str]]:
    draw = node.find(f"{HP}drawText")
    if draw is None:
        return False, []
    paragraphs = []
    for para in draw.iter(f"{HP}p"):
        paragraphs.append("".join((t.text or "") for t in para.iter(f"{HP}t")))
    return True, paragraphs


def _object_payload(section: str, section_index: int, index: int, node, para_ord: dict[int, int], para_map: dict) -> dict:
    owner = node.getparent()
    while owner is not None and _local(owner.tag) != "p":
        owner = owner.getparent()
    paragraph_index = para_ord.get(id(owner), -1)
    paragraph = para_map.get((section, paragraph_index))
    locator, stability = _drawing_locator(section, index, node)
    sz = node.find(f"{HP}sz")
    pos = node.find(f"{HP}pos")
    rot = node.find(f"{HP}rotationInfo")
    flip = node.find(f"{HP}flip")
    has_textbox, text_paragraphs = _text_payload(node)
    child_shapes = []
    if _local(node.tag) == "container":
        for child in node.iter():
            if child is node or _local(child.tag) not in DRAWING_TAGS:
                continue
            child_shapes.append({
                "kind": _local(child.tag),
                "id": child.get("id"),
                "instid": child.get("instid"),
            })
    return {
        "locator": locator,
        "address_stability": stability,
        "kind": _local(node.tag),
        "id": node.get("id"),
        "instid": node.get("instid"),
        "section_index": section_index,
        "section": section,
        "anchor_paragraph_index": paragraph_index,
        "anchor_locator": None if paragraph is None else paragraph["locator"],
        "width": None if sz is None else int(sz.get("width", "0") or 0),
        "height": None if sz is None else int(sz.get("height", "0") or 0),
        "position": None if pos is None else dict(sorted(pos.attrib.items())),
        "placement": (
            None if pos is None else
            ("inline" if str(pos.get("treatAsChar", "")).lower() in {"1", "true"} else "floating")
        ),
        "text_wrap": node.get("textWrap"),
        "text_flow": node.get("textFlow"),
        "z_order": None if node.get("zOrder") is None else int(node.get("zOrder", "0") or 0),
        "lock": node.get("lock"),
        "group_level": node.get("groupLevel"),
        "rotation": None if rot is None else dict(sorted(rot.attrib.items())),
        "flip": None if flip is None else dict(sorted(flip.attrib.items())),
        "has_textbox": has_textbox,
        "text_paragraphs": text_paragraphs,
        "text": "\n".join(text_paragraphs),
        "group_children": child_shapes,
    }


def build_drawing_layer_map(path: Path) -> dict:
    para_map = _paragraph_map(path)
    objects = []
    with zipfile.ZipFile(path, "r") as archive:
        sections = sorted(
            name for name in archive.namelist()
            if name.startswith("Contents/section") and name.endswith(".xml")
        )
        for section_index, section in enumerate(sections):
            root = etree.fromstring(archive.read(section))
            paras = _paragraphs(root)
            para_ord = {id(node): index for index, node in enumerate(paras)}
            for node in root.iter():
                if _local(node.tag) not in DRAWING_TAGS:
                    continue
                objects.append(_object_payload(
                    section, section_index, len(objects), node, para_ord, para_map
                ))
    structure_seed = [
        {
            "locator": item["locator"],
            "kind": item["kind"],
            "anchor_locator": item["anchor_locator"],
            "id": item["id"],
            "instid": item["instid"],
            "has_textbox": item["has_textbox"],
            "group_children": item["group_children"],
        }
        for item in objects
    ]
    geometry_seed = [
        {
            "locator": item["locator"],
            "width": item["width"],
            "height": item["height"],
            "position": item["position"],
            "text_wrap": item["text_wrap"],
            "text_flow": item["text_flow"],
            "z_order": item["z_order"],
            "rotation": item["rotation"],
            "flip": item["flip"],
        }
        for item in objects
    ]
    family_counts = {
        kind: sum(1 for item in objects if item["kind"] == kind)
        for kind in sorted({item["kind"] for item in objects})
    }
    return {
        "schema": SCHEMA,
        "drawing_count": len(objects),
        "family_counts": family_counts,
        "objects": objects,
        "drawing_structure_sha256": _sha(structure_seed),
        "drawing_geometry_sha256": _sha(geometry_seed),
        "contract": drawing_layer_contract(),
    }


def _resolve(mapped: dict, locator: object) -> dict:
    value = str(locator or "")
    found = next((item for item in mapped["objects"] if item["locator"] == value), None)
    if found is None:
        raise ValueError(f"Unknown drawing locator: {value}")
    return found


def _bounded_int(value: object, name: str, low: int, high: int) -> int:
    result = int(value)
    if result < low or result > high:
        raise ValueError(f"{name} is outside admitted bounds")
    return result


def _mutate_section(path: Path, section_name: str, mutator: Callable[[Any], Any]) -> Any:
    fd, tmp_name = tempfile.mkstemp(prefix=path.stem + ".p325-xml-", suffix=".hwpx", dir=str(path.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    result = None
    try:
        with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(tmp, "w") as target:
            for info in source.infolist():
                payload = source.read(info.filename)
                if info.filename == section_name:
                    root = etree.fromstring(payload)
                    result = mutator(root)
                    payload = etree.tostring(root, encoding="UTF-8", xml_declaration=True, standalone=True)
                target.writestr(info, payload)
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
    return result


def _find_node(root, target: dict):
    candidates = [node for node in root.iter() if _local(node.tag) in DRAWING_TAGS]
    intrinsic = target.get("instid") or target.get("id")
    if intrinsic:
        node = next(
            (
                item for item in candidates
                if (item.get("instid") or item.get("id")) == intrinsic
                and _local(item.tag) == target["kind"]
            ),
            None,
        )
        if node is not None:
            return node
    ordinal = int(target["locator"].split("_", 1)[-1], 16) if False else None
    matches = [item for item in candidates if _local(item.tag) == target["kind"]]
    if len(matches) == 1:
        return matches[0]
    raise ValueError("drawing locator lost intrinsic identity and cannot be safely rebound")


def _apply_layout_node(node, op: dict) -> dict:
    if "text_wrap" in op:
        wrap = str(op["text_wrap"]).upper()
        if wrap not in WRAP_MODES:
            raise ValueError(f"unsupported text_wrap: {wrap}")
        node.set("textWrap", wrap)
    if "text_flow" in op:
        node.set("textFlow", str(op["text_flow"]).upper())
    if "z_order" in op:
        node.set("zOrder", str(_bounded_int(op["z_order"], "z_order", -1_000_000, 1_000_000)))
    if "lock" in op:
        node.set("lock", "1" if bool(op["lock"]) else "0")

    pos = node.find(f"{HP}pos")
    position_fields = {
        "treat_as_char": "treatAsChar",
        "affect_line_spacing": "affectLSpacing",
        "flow_with_text": "flowWithText",
        "allow_overlap": "allowOverlap",
        "hold_anchor": "holdAnchorAndSO",
        "vert_rel_to": "vertRelTo",
        "horz_rel_to": "horzRelTo",
        "vert_align": "vertAlign",
        "horz_align": "horzAlign",
        "vertical_offset": "vertOffset",
        "horizontal_offset": "horzOffset",
    }
    requested_position = any(key in op for key in position_fields)
    if requested_position and pos is None:
        raise ValueError("drawing object has no hp:pos and cannot accept anchor-layout edits")
    if pos is not None:
        for field, attr in position_fields.items():
            if field not in op:
                continue
            value = op[field]
            if field in {"treat_as_char", "affect_line_spacing", "flow_with_text", "allow_overlap", "hold_anchor"}:
                pos.set(attr, "1" if bool(value) else "0")
            elif field in {"vertical_offset", "horizontal_offset"}:
                pos.set(attr, str(_bounded_int(value, field, -10_000_000, 10_000_000)))
            else:
                pos.set(attr, str(value).upper())
    return {
        "text_wrap": node.get("textWrap"),
        "text_flow": node.get("textFlow"),
        "z_order": node.get("zOrder"),
        "position": None if pos is None else dict(pos.attrib),
    }


def _resize_node(node, width: int, height: int) -> None:
    width = _bounded_int(width, "width", 1, 10_000_000)
    height = _bounded_int(height, "height", 1, 10_000_000)
    for tag in ("sz", "orgSz", "curSz"):
        child = node.find(f"{HP}{tag}")
        if child is not None:
            child.set("width", str(width))
            child.set("height", str(height))
    rot = node.find(f"{HP}rotationInfo")
    if rot is not None:
        rot.set("centerX", str(width // 2))
        rot.set("centerY", str(height // 2))
    if _local(node.tag) == "rect":
        points = { _local(child.tag): child for child in node if _local(child.tag) in {"pt0","pt1","pt2","pt3"} }
        coords = {"pt0":(0,0), "pt1":(width,0), "pt2":(width,height), "pt3":(0,height)}
        for tag, (x, y) in coords.items():
            if tag in points:
                points[tag].set("x", str(x))
                points[tag].set("y", str(y))


def _insert_textbox(path: Path, op: dict, *, strip_text: bool) -> dict:
    paragraphs = op.get("paragraphs")
    if paragraphs is None:
        paragraphs = [str(op.get("text", ""))]
    if not isinstance(paragraphs, list) or not paragraphs:
        raise ValueError("textbox/rectangle authoring requires text or a non-empty paragraphs list")
    receipt = inject_textbox(
        path,
        anchor_locator=str(op.get("anchor") or ""),
        paragraphs=[str(item) for item in paragraphs],
        width=_bounded_int(op.get("width", 14400), "width", 1, 10_000_000),
        height=_bounded_int(op.get("height", 7200), "height", 1, 10_000_000),
        treat_as_char=bool(op.get("treat_as_char", False)),
        horizontal_offset=_bounded_int(op.get("horizontal_offset", 0), "horizontal_offset", -10_000_000, 10_000_000),
        vertical_offset=_bounded_int(op.get("vertical_offset", 0), "vertical_offset", -10_000_000, 10_000_000),
        horz_rel_to=str(op.get("horz_rel_to", "PARA")).upper(),
        vert_rel_to=str(op.get("vert_rel_to", "PARA")).upper(),
        z_order=_bounded_int(op.get("z_order", 0), "z_order", -1_000_000, 1_000_000),
        shape_seed=str(op.get("shape_seed", "p325")),
    )
    if strip_text:
        mapped = build_drawing_layer_map(path)
        created = next(
            (
                item for item in mapped["objects"]
                if item["kind"] == "rect" and item.get("id") == receipt["shape_id"]
            ),
            None,
        )
        if created is None:
            raise ValueError("insert_rectangle could not reacquire created rectangle")
        def mutate(root):
            node = _find_node(root, created)
            draw = node.find(f"{HP}drawText")
            if draw is not None:
                node.remove(draw)
        _mutate_section(path, created["section"], mutate)
    return receipt


def _apply_one(path: Path, op: dict) -> dict:
    name = str(op.get("op") or "")
    if name in DEFERRED_OPERATIONS:
        raise ValueError(DEFERRED_OPERATIONS[name])
    if name == "insert_textbox":
        return {"op": name, **_insert_textbox(path, op, strip_text=False)}
    if name == "insert_rectangle":
        return {"op": name, **_insert_textbox(path, {**op, "paragraphs": [""]}, strip_text=True)}

    mapped = build_drawing_layer_map(path)
    target = _resolve(mapped, op.get("drawing"))
    section = target["section"]

    if name == "set_drawing_layout":
        def mutate(root):
            node = _find_node(root, target)
            return _apply_layout_node(node, op)
        return {"op": name, "drawing": target["locator"], **(_mutate_section(path, section, mutate) or {})}

    if name == "resize_drawing_object":
        if target["kind"] not in RESIZABLE_KINDS:
            raise ValueError(f"resize is not admitted for drawing family {target['kind']}")
        width = int(op["width"])
        height = int(op["height"])
        def mutate(root):
            _resize_node(_find_node(root, target), width, height)
        _mutate_section(path, section, mutate)
        return {"op": name, "drawing": target["locator"], "width": width, "height": height}

    if name == "rotate_drawing_object":
        angle = _bounded_int(op.get("angle", 0), "angle", -360, 360)
        def mutate(root):
            node = _find_node(root, target)
            rot = node.find(f"{HP}rotationInfo")
            if rot is None:
                raise ValueError("drawing object has no rotationInfo")
            rot.set("angle", str(angle))
        _mutate_section(path, section, mutate)
        return {"op": name, "drawing": target["locator"], "angle": angle}

    if name == "flip_drawing_object":
        horizontal = bool(op.get("horizontal", False))
        vertical = bool(op.get("vertical", False))
        def mutate(root):
            node = _find_node(root, target)
            flip = node.find(f"{HP}flip")
            if flip is None:
                raise ValueError("drawing object has no flip element")
            flip.set("horizontal", "1" if horizontal else "0")
            flip.set("vertical", "1" if vertical else "0")
        _mutate_section(path, section, mutate)
        return {
            "op": name,
            "drawing": target["locator"],
            "horizontal": horizontal,
            "vertical": vertical,
        }

    if name == "remove_drawing_object":
        def mutate(root):
            node = _find_node(root, target)
            parent = node.getparent()
            if parent is None:
                raise ValueError("drawing object has no mutable parent")
            parent.remove(node)
            grand = parent.getparent()
            if grand is not None and _local(parent.tag) == "run" and len(parent) == 0:
                grand.remove(parent)
        _mutate_section(path, section, mutate)
        return {"op": name, "drawing": target["locator"], "removed_kind": target["kind"]}

    raise ValueError(f"Unsupported drawing-layer operation: {name}")


def _rebinding(before: dict, after: dict) -> dict:
    b = {item["locator"] for item in before["objects"]}
    a = {item["locator"] for item in after["objects"]}
    return {
        "created_drawings": sorted(a - b),
        "deleted_drawings": sorted(b - a),
        "stable_drawings": sorted(a & b),
        "reacquire_required": bool(a != b),
    }


def apply_drawing_layer_atomic(
    path: Path,
    operations: list[dict],
    *,
    expected_revision: int,
    current_revision: int,
    validator: Callable[[Path], dict] | None = None,
) -> dict:
    if int(expected_revision) != int(current_revision):
        raise ValueError(f"Stale revision: expected {expected_revision}, current {current_revision}")
    if not operations or len(operations) > 64:
        raise ValueError("Drawing-layer transaction requires 1..64 operations")
    if not all(isinstance(op, dict) for op in operations):
        raise ValueError("Each drawing-layer operation must be an object")

    before = build_drawing_layer_map(path)
    fd, tmp_name = tempfile.mkstemp(prefix=path.stem + ".p325-drawing-", suffix=".hwpx", dir=str(path.parent))
    os.close(fd)
    candidate = Path(tmp_name)
    candidate.write_bytes(path.read_bytes())
    receipts = []
    validation = None
    try:
        for op in operations:
            receipts.append(_apply_one(candidate, op))
        after = build_drawing_layer_map(candidate)
        if validator is not None:
            validation = validator(candidate)
        os.replace(candidate, path)
    except Exception:
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass
        raise

    return {
        "before": {
            "drawing_count": before["drawing_count"],
            "drawing_structure_sha256": before["drawing_structure_sha256"],
            "drawing_geometry_sha256": before["drawing_geometry_sha256"],
        },
        "after": {
            "drawing_count": after["drawing_count"],
            "drawing_structure_sha256": after["drawing_structure_sha256"],
            "drawing_geometry_sha256": after["drawing_geometry_sha256"],
        },
        "drawing_structure_changed": before["drawing_structure_sha256"] != after["drawing_structure_sha256"],
        "drawing_geometry_changed": before["drawing_geometry_sha256"] != after["drawing_geometry_sha256"],
        "drawing_rebinding": _rebinding(before, after),
        "operation_count": len(operations),
        "receipts": receipts,
        "validation": validation,
        "authority": "STRUCTURAL_DRAWING_LAYER_AUTHORITY_ONLY",
        "native_render_batch_status": "DEFERRED_BY_DESIGN",
    }
