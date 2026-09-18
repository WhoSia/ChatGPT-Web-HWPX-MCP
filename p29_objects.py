from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Callable

from hwpx import HwpxDocument
from hwpx.oxml.paragraph import HwpxOxmlParagraph

from p2_document import build_document_map
from p28_tables import _save_document

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HC = "{http://www.hancom.co.kr/hwpml/2011/core}"
MAX_IMAGE_BYTES = 8 * 1024 * 1024
ADMITTED_FORMATS = {"png", "jpg", "jpeg"}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _object_locator(section_index: int, picture_index: int, element) -> tuple[str, str]:
    intrinsic = element.get("instid") or element.get("id")
    if intrinsic:
        seed = f"section:{section_index}\0pic-id\0{intrinsic}"
        stability = "intrinsic-id"
    else:
        seed = f"section:{section_index}\0pic-ordinal\0{picture_index}"
        stability = "revision-bound-ordinal"
    return "o_" + hashlib.sha256(seed.encode()).hexdigest()[:20], stability


def _paragraph_locator_lookup(path: Path) -> dict[tuple[int, int], dict]:
    mapped = build_document_map(path)
    return {
        (int(p["section_index"]), int(p["paragraph_index"])): p
        for p in mapped["paragraphs"]
    }


def _paragraphs(section) -> list:
    return [node for node in section.element.iter() if _local(node.tag) == "p"]


def _pictures(document) -> list[dict]:
    result: list[dict] = []
    paragraph_lookup: dict[tuple[int, int], HwpxOxmlParagraph] = {}
    global_index = 0
    for section_index, section in enumerate(document._root.sections):
        paras = _paragraphs(section)
        para_ord = {id(node): index for index, node in enumerate(paras)}
        for node in section.element.iter():
            if _local(node.tag) != "pic":
                continue
            parent = node.getparent() if hasattr(node, "getparent") else None
            owner = parent
            while owner is not None and _local(owner.tag) != "p":
                owner = owner.getparent() if hasattr(owner, "getparent") else None
            paragraph_index = para_ord.get(id(owner), -1)
            if paragraph_index >= 0 and (section_index, paragraph_index) not in paragraph_lookup:
                paragraph_lookup[(section_index, paragraph_index)] = HwpxOxmlParagraph(owner, section)
            locator, stability = _object_locator(section_index, global_index, node)
            image = node.find(f"{HC}img")
            sz = node.find(f"{HP}sz")
            pos = node.find(f"{HP}pos")
            result.append({
                "locator": locator,
                "address_stability": stability,
                "intrinsic_id": node.get("instid") or node.get("id"),
                "picture_index": global_index,
                "section_index": section_index,
                "paragraph_index": paragraph_index,
                "element": node,
                "paragraph": paragraph_lookup.get((section_index, paragraph_index)),
                "binary_item_id_ref": None if image is None else image.get("binaryItemIDRef"),
                "width": None if sz is None else int(sz.get("width", "0") or 0),
                "height": None if sz is None else int(sz.get("height", "0") or 0),
                "treat_as_char": None if pos is None else pos.get("treatAsChar"),
                "position": None if pos is None else dict(pos.attrib),
                "text_wrap": node.get("textWrap"),
                "z_order": node.get("zOrder"),
                "lock": node.get("lock"),
            })
            global_index += 1
    return result


def _media_items(document) -> list[dict]:
    refs: dict[str, int] = {}
    for pic in _pictures(document):
        ref = pic["binary_item_id_ref"]
        if ref:
            refs[ref] = refs.get(ref, 0) + 1
    items: list[dict] = []
    for item in document.media.images:
        item_id = str(item.item_id)
        digest = None
        if item.href and document._package.has_part(item.href):
            digest = hashlib.sha256(document._package.read(item.href)).hexdigest()
        items.append({
            "item_id": item_id,
            "format": item.format,
            "href": item.href,
            "bytes": item.size,
            "sha256": digest,
            "picture_reference_count": refs.get(item_id, 0),
            "orphaned": refs.get(item_id, 0) == 0,
        })
    return items


def build_object_map(path: Path) -> dict:
    document = HwpxDocument.open(str(path))
    try:
        para_map = _paragraph_locator_lookup(path)
        pictures = []
        geometry_seed = []
        topology_seed = []
        for pic in _pictures(document):
            paragraph = para_map.get((pic["section_index"], pic["paragraph_index"]))
            payload = {
                key: value
                for key, value in pic.items()
                if key not in {"element", "paragraph"}
            }
            payload["paragraph_locator"] = None if paragraph is None else paragraph["locator"]
            payload["placement"] = (
                "inline"
                if str(pic["treat_as_char"]).lower() in {"1", "true"}
                else "floating"
            )
            pictures.append(payload)
            topology_seed.append({
                "locator": payload["locator"],
                "section_index": payload["section_index"],
                "paragraph_locator": payload["paragraph_locator"],
                "binary_item_id_ref": payload["binary_item_id_ref"],
                "placement": payload["placement"],
            })
            geometry_seed.append({
                "locator": payload["locator"],
                "width": payload["width"],
                "height": payload["height"],
                "position": payload["position"],
                "text_wrap": payload["text_wrap"],
                "z_order": payload["z_order"],
                "lock": payload["lock"],
            })
        media = _media_items(document)
        media_seed = [
            {
                "item_id": item["item_id"],
                "format": item["format"],
                "bytes": item["bytes"],
                "sha256": item["sha256"],
                "picture_reference_count": item["picture_reference_count"],
            }
            for item in media
        ]
        digest = lambda value: hashlib.sha256(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return {
            "pictures": pictures,
            "picture_count": len(pictures),
            "media_items": media,
            "media_item_count": len(media),
            "object_structure_sha256": digest(topology_seed),
            "object_geometry_sha256": digest(geometry_seed),
            "media_custody_sha256": digest(media_seed),
        }
    finally:
        document.close()


def _resolve_picture(mapped: dict, locator: object) -> dict:
    value = str(locator or "")
    found = next((item for item in mapped["pictures"] if item["locator"] == value), None)
    if found is None:
        raise ValueError(f"Unknown picture locator: {value}")
    return found


def _decode_image(op: dict) -> tuple[bytes, str]:
    raw = op.get("content_base64")
    if not isinstance(raw, str) or not raw:
        raise ValueError("content_base64 is required")
    try:
        data = base64.b64decode(raw, validate=True)
    except Exception as exc:
        raise ValueError("content_base64 is not valid base64") from exc
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("image bytes are empty or exceed the 8 MiB custody bound")
    fmt = str(op.get("image_format", "")).lower().lstrip(".")
    if fmt not in ADMITTED_FORMATS:
        raise ValueError("image_format must be png, jpg, or jpeg")
    if fmt == "png" and not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("PNG signature mismatch")
    if fmt in {"jpg", "jpeg"} and not (len(data) >= 3 and data[:3] == b"\xff\xd8\xff"):
        raise ValueError("JPEG signature mismatch")
    return data, fmt


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


def _set_picture_size(element, width: int, height: int) -> None:
    if width <= 0 or height <= 0 or width > 10_000_000 or height > 10_000_000:
        raise ValueError("picture width/height are outside admitted HWPUNIT bounds")
    for name in ("sz", "orgSz", "curSz"):
        child = element.find(f"{HP}{name}")
        if child is not None:
            child.set("width", str(width))
            child.set("height", str(height))
    rot = element.find(f"{HP}rotationInfo")
    if rot is not None:
        rot.set("centerX", str(width // 2))
        rot.set("centerY", str(height // 2))
    rect = element.find(f"{HP}imgRect")
    if rect is not None:
        points = [child for child in rect if _local(child.tag).startswith("pt")]
        coords = ((0, 0), (width, 0), (width, height), (0, height))
        for point, (x, y) in zip(points, coords):
            point.set("x", str(x))
            point.set("y", str(y))
    clip = element.find(f"{HP}imgClip")
    if clip is not None:
        clip.set("left", "0")
        clip.set("right", str(width))
        clip.set("top", "0")
        clip.set("bottom", str(height))
    dim = element.find(f"{HP}imgDim")
    if dim is not None:
        dim.set("dimwidth", str(width))
        dim.set("dimheight", str(height))


def _remove_picture(document, picture: dict, *, remove_orphaned: bool) -> dict:
    current = _pictures(document)
    target = current[int(picture["picture_index"])]
    element = target["element"]
    parent = element.getparent() if hasattr(element, "getparent") else None
    if parent is None:
        raise ValueError("picture has no mutable run parent")
    old_ref = target["binary_item_id_ref"]
    parent.remove(element)
    run_parent = parent.getparent() if hasattr(parent, "getparent") else None
    if len(parent) == 0 and run_parent is not None and _local(parent.tag) == "run":
        run_parent.remove(parent)
    section = document._root.sections[int(target["section_index"])]
    section.mark_dirty()
    removed_media = False
    if remove_orphaned and old_ref:
        remaining = _pictures(document)
        if not any(item["binary_item_id_ref"] == old_ref for item in remaining):
            removed_media = document.media.remove_image(old_ref)
    return {"removed_picture": picture["locator"], "removed_media_item": old_ref if removed_media else None}


def _apply_one(candidate: Path, op: dict) -> dict:
    name = op.get("op")
    mapped = build_object_map(candidate)
    document = HwpxDocument.open(str(candidate))
    try:
        if name == "insert_picture":
            data, fmt = _decode_image(op)
            paragraph, target = _resolve_paragraph(document, candidate, op.get("paragraph"))
            width = int(op.get("width", 14400))
            height = int(op.get("height", 14400))
            if width <= 0 or height <= 0:
                raise ValueError("picture width/height must be positive")
            item = document.media.add_image(data, fmt)
            placement = str(op.get("placement", "inline")).lower()
            if placement not in {"inline", "floating"}:
                raise ValueError("placement must be inline or floating")
            pos_overrides = None
            text_wrap = op.get("text_wrap")
            if placement == "floating":
                pos_overrides = {
                    "horzRelTo": str(op.get("horz_rel_to", "COLUMN")).upper(),
                    "vertRelTo": str(op.get("vert_rel_to", "PARA")).upper(),
                    "horzAlign": str(op.get("horz_align", "LEFT")).upper(),
                    "vertAlign": str(op.get("vert_align", "TOP")).upper(),
                    "horzOffset": int(op.get("horizontal_offset", 0)),
                    "vertOffset": int(op.get("vertical_offset", 0)),
                }
            paragraph.add_picture(
                str(item),
                width=width,
                height=height,
                treat_as_char=placement == "inline",
                pos_overrides=pos_overrides,
                text_wrap=None if text_wrap is None else str(text_wrap).upper(),
            )
            _save_document(document, candidate, candidate)
            after = build_object_map(candidate)
            created = [p for p in after["pictures"] if p["locator"] not in {x["locator"] for x in mapped["pictures"]}]
            if len(created) != 1:
                raise ValueError("insert_picture did not yield one uniquely identifiable object")
            return {"op": name, "created_picture": created[0]["locator"], "media_item_id": str(item), "paragraph": target["locator"]}

        picture = _resolve_picture(mapped, op.get("picture"))
        if name == "replace_picture":
            data, fmt = _decode_image(op)
            replacement = document.media.replace_picture(
                data,
                fmt,
                picture_index=int(picture["picture_index"]),
                remove_orphaned=bool(op.get("remove_orphaned", True)),
            )
            _save_document(document, candidate, candidate)
            return {
                "op": name,
                "picture": picture["locator"],
                "media_item_id": str(replacement.item_id),
                "previous_media_item_id": replacement.previous_item_id,
                "removed_orphans": list(replacement.removed_orphans),
            }
        if name == "remove_picture":
            receipt = _remove_picture(document, picture, remove_orphaned=bool(op.get("remove_orphaned", True)))
            _save_document(document, candidate, candidate)
            return {"op": name, **receipt}
        if name == "resize_picture":
            current = _pictures(document)[int(picture["picture_index"])]
            _set_picture_size(current["element"], int(op["width"]), int(op["height"]))
            document._root.sections[int(current["section_index"])].mark_dirty()
            _save_document(document, candidate, candidate)
            return {"op": name, "picture": picture["locator"], "width": int(op["width"]), "height": int(op["height"])}
        if name == "set_picture_position":
            current = _pictures(document)[int(picture["picture_index"])]
            pos = current["element"].find(f"{HP}pos")
            if pos is None or str(pos.get("treatAsChar", "")).lower() not in {"0", "false"}:
                raise ValueError("set_picture_position requires an existing floating picture")
            for field, attr in (("horizontal_offset", "horzOffset"), ("vertical_offset", "vertOffset")):
                if field in op:
                    value = int(op[field])
                    if value < 0 or value > 2**31 - 1:
                        raise ValueError(f"{field} is outside schema-backed bounds")
                    pos.set(attr, str(value))
            document._root.sections[int(current["section_index"])].mark_dirty()
            _save_document(document, candidate, candidate)
            return {"op": name, "picture": picture["locator"], "position": dict(pos.attrib)}
        raise ValueError(f"Unsupported object operation: {name}")
    finally:
        document.close()


def _rebinding(before: dict, after: dict) -> dict:
    b = {p["locator"] for p in before["pictures"]}
    a = {p["locator"] for p in after["pictures"]}
    return {
        "created_pictures": sorted(a - b),
        "deleted_pictures": sorted(b - a),
        "stable_pictures": sorted(a & b),
        "reacquire_required": bool(a != b),
    }


def apply_object_edits_atomic(
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
        raise ValueError("Object transaction requires 1..20 operations")
    if not all(isinstance(op, dict) for op in operations):
        raise ValueError("Each object operation must be an object")

    before = build_object_map(path)
    fd, tmp_name = tempfile.mkstemp(prefix=path.stem + ".p29-", suffix=".hwpx", dir=str(path.parent))
    os.close(fd)
    candidate = Path(tmp_name)
    candidate.write_bytes(path.read_bytes())
    receipts: list[dict] = []
    validation = None
    try:
        for op in operations:
            receipts.append(_apply_one(candidate, op))
        after = build_object_map(candidate)
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
            "picture_count": before["picture_count"],
            "media_item_count": before["media_item_count"],
            "object_structure_sha256": before["object_structure_sha256"],
            "object_geometry_sha256": before["object_geometry_sha256"],
            "media_custody_sha256": before["media_custody_sha256"],
        },
        "after": {
            "picture_count": after["picture_count"],
            "media_item_count": after["media_item_count"],
            "object_structure_sha256": after["object_structure_sha256"],
            "object_geometry_sha256": after["object_geometry_sha256"],
            "media_custody_sha256": after["media_custody_sha256"],
        },
        "object_structure_changed": before["object_structure_sha256"] != after["object_structure_sha256"],
        "object_geometry_changed": before["object_geometry_sha256"] != after["object_geometry_sha256"],
        "media_custody_changed": before["media_custody_sha256"] != after["media_custody_sha256"],
        "object_rebinding": _rebinding(before, after),
        "operation_count": len(operations),
        "receipts": receipts,
    }
    if validation is not None:
        result["validation"] = validation
    return result
