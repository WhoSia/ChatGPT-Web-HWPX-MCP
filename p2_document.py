from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Callable
from xml.etree import ElementTree

SECTION_PREFIX = "Contents/section"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _norm_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _paragraph_text(node: ElementTree.Element) -> str:
    chunks: list[str] = []
    for elem in node.iter():
        if _local(elem.tag) == "t" and elem.text:
            chunks.append(elem.text)
    return "".join(chunks)


def _paragraph_intrinsic_id(node: ElementTree.Element) -> str | None:
    for key, value in node.attrib.items():
        if _local(key).lower() == "id" and value:
            return str(value)
    return None


def _set_intrinsic_id(node: ElementTree.Element, value: str) -> None:
    for key in list(node.attrib):
        if _local(key).lower() == "id":
            node.attrib[key] = value
            return
    node.set("id", value)


def _stable_locator(section_name: str, paragraph_index: int, node: ElementTree.Element) -> tuple[str, str]:
    intrinsic = _paragraph_intrinsic_id(node)
    if intrinsic is not None:
        seed = f"{section_name}\0id\0{intrinsic}"
        stability = "intrinsic-id"
    else:
        seed = f"{section_name}\0ordinal\0{paragraph_index}"
        stability = "revision-bound-ordinal"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]
    return f"p_{digest}", stability


def _section_names(archive: zipfile.ZipFile) -> list[str]:
    names = []
    for name in archive.namelist():
        if name.startswith(SECTION_PREFIX) and name.lower().endswith(".xml"):
            names.append(name)
    return sorted(names)


def build_document_map(path: Path) -> dict:
    paragraphs: list[dict] = []
    sections: list[dict] = []
    text_parts: list[str] = []
    with zipfile.ZipFile(path, "r") as archive:
        for section_index, section_name in enumerate(_section_names(archive)):
            root = ElementTree.fromstring(archive.read(section_name))
            section_paragraphs: list[str] = []
            para_index = 0
            for node in root.iter():
                if _local(node.tag) != "p":
                    continue
                text = _paragraph_text(node)
                locator, stability = _stable_locator(section_name, para_index, node)
                intrinsic_id = _paragraph_intrinsic_id(node)
                paragraph = {
                    "locator": locator,
                    "kind": "paragraph",
                    "section": section_name,
                    "section_index": section_index,
                    "paragraph_index": para_index,
                    "intrinsic_id": intrinsic_id,
                    "address_stability": stability,
                    "text": text,
                    "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                }
                paragraphs.append(paragraph)
                section_paragraphs.append(locator)
                text_parts.append(text)
                para_index += 1
            sections.append(
                {
                    "section": section_name,
                    "section_index": section_index,
                    "paragraph_count": para_index,
                    "paragraph_locators": section_paragraphs,
                }
            )
    joined = "\n".join(text_parts)
    semantic_digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    structure_seed = json.dumps(
        [(p["section"], p["paragraph_index"], p["locator"], p["intrinsic_id"]) for p in paragraphs],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return {
        "sections": sections,
        "paragraphs": paragraphs,
        "paragraph_count": len(paragraphs),
        "text": joined,
        "text_chars": len(joined),
        "semantic_sha256": semantic_digest,
        "structure_sha256": hashlib.sha256(structure_seed.encode("utf-8")).hexdigest(),
    }


def _paragraph_index_by_locator(document_map: dict) -> dict[str, dict]:
    return {item["locator"]: item for item in document_map["paragraphs"]}


def _replace_paragraph_text(node: ElementTree.Element, new_text: str) -> tuple[str, str]:
    before = _paragraph_text(node)
    text_nodes = [elem for elem in node.iter() if _local(elem.tag) == "t"]
    if not text_nodes:
        raise ValueError("Target paragraph has no editable text node")
    text_nodes[0].text = new_text
    for elem in text_nodes[1:]:
        elem.text = ""
    return before, new_text


def _parent_map(root: ElementTree.Element) -> dict[ElementTree.Element, ElementTree.Element]:
    return {child: parent for parent in root.iter() for child in parent}


def _paragraph_nodes(root: ElementTree.Element) -> list[ElementTree.Element]:
    return [node for node in root.iter() if _local(node.tag) == "p"]


def _fresh_paragraph_id(root: ElementTree.Element) -> str:
    used: set[str] = set()
    numeric: list[int] = []
    for node in _paragraph_nodes(root):
        intrinsic = _paragraph_intrinsic_id(node)
        if intrinsic is None:
            continue
        used.add(intrinsic)
        try:
            numeric.append(int(intrinsic))
        except ValueError:
            pass
    candidate = (max(numeric) + 1) if numeric else 1
    while str(candidate) in used:
        candidate += 1
    return str(candidate)


def _clone_paragraph(anchor: ElementTree.Element, text: str, root: ElementTree.Element) -> ElementTree.Element:
    """Clone paragraph formatting without duplicating controls or rich inline content."""
    node = copy.deepcopy(anchor)
    _set_intrinsic_id(node, _fresh_paragraph_id(root))

    direct_runs = [child for child in list(node) if _local(child.tag) == "run"]
    if not direct_runs:
        raise ValueError("Paragraph template has no direct editable run")
    run = direct_runs[0]
    text_template = next((elem for elem in run.iter() if _local(elem.tag) == "t"), None)
    if text_template is None:
        raise ValueError("Paragraph template has no editable text node")

    for child in list(node):
        if _local(child.tag) == "run" and child is not run:
            node.remove(child)
        elif _local(child.tag).lower() == "linesegarray":
            node.remove(child)

    new_text = copy.deepcopy(text_template)
    for child in list(new_text):
        new_text.remove(child)
    new_text.text = text
    new_text.tail = None
    for child in list(run):
        run.remove(child)
    run.append(new_text)
    return node


def _insert_relative(
    root: ElementTree.Element,
    anchor: ElementTree.Element,
    new_node: ElementTree.Element,
    *,
    after: bool,
) -> None:
    parents = _parent_map(root)
    parent = parents.get(anchor)
    if parent is None:
        raise ValueError("Paragraph anchor has no mutable parent")
    siblings = list(parent)
    index = siblings.index(anchor) + (1 if after else 0)
    parent.insert(index, new_node)


def _delete_node(root: ElementTree.Element, node: ElementTree.Element) -> None:
    parent = _parent_map(root).get(node)
    if parent is None:
        raise ValueError("Paragraph target has no mutable parent")
    parent.remove(node)


def _move_relative(
    root: ElementTree.Element,
    source: ElementTree.Element,
    anchor: ElementTree.Element,
    *,
    after: bool,
) -> None:
    if source is anchor:
        raise ValueError("Move source and anchor must be different paragraphs")
    parents = _parent_map(root)
    source_parent = parents.get(source)
    anchor_parent = parents.get(anchor)
    if source_parent is None or anchor_parent is None:
        raise ValueError("Move source/anchor has no mutable parent")
    if source_parent is not anchor_parent:
        raise ValueError("Cross-container paragraph moves are not supported in P2.1")
    source_parent.remove(source)
    siblings = list(anchor_parent)
    index = siblings.index(anchor) + (1 if after else 0)
    anchor_parent.insert(index, source)


def _identity_key(item: dict) -> tuple[str, str] | None:
    intrinsic = item.get("intrinsic_id")
    if intrinsic is None:
        return None
    return item["section"], str(intrinsic)


def _locator_rebinding(before_map: dict, after_map: dict) -> dict:
    after_by_identity = {
        key: item
        for item in after_map["paragraphs"]
        if (key := _identity_key(item)) is not None
    }
    bindings: list[dict] = []
    invalidated: list[str] = []
    for before in before_map["paragraphs"]:
        key = _identity_key(before)
        if key is None:
            invalidated.append(before["locator"])
            continue
        after = after_by_identity.get(key)
        bindings.append(
            {
                "before_locator": before["locator"],
                "after_locator": None if after is None else after["locator"],
                "status": "deleted" if after is None else (
                    "stable" if after["locator"] == before["locator"] else "rebound"
                ),
                "intrinsic_id": before["intrinsic_id"],
            }
        )
    return {
        "bindings": bindings,
        "invalidated_revision_bound_locators": invalidated,
        "reacquire_required": bool(invalidated),
    }


def _normalize_operations(operations: list[dict], locator_index: dict[str, dict]) -> list[dict]:
    normalized: list[dict] = []
    mutated_targets: set[str] = set()
    for raw in operations:
        if not isinstance(raw, dict):
            raise ValueError("Each edit operation must be an object")
        op = raw.get("op")
        if op == "replace_paragraph_text":
            locator = raw.get("target")
            if not isinstance(locator, str) or locator not in locator_index:
                raise ValueError(f"Unknown paragraph locator: {locator}")
            if locator in mutated_targets:
                raise ValueError(f"Duplicate mutation target in one transaction: {locator}")
            text = raw.get("text")
            if not isinstance(text, str):
                raise ValueError("replace_paragraph_text requires string text")
            if len(text) > 100_000:
                raise ValueError("Replacement text is too large")
            mutated_targets.add(locator)
            normalized.append({"op": op, "target": locator, "text": _norm_text(text)})
            continue

        if op in {"insert_paragraph_before", "insert_paragraph_after"}:
            anchor = raw.get("target")
            if not isinstance(anchor, str) or anchor not in locator_index:
                raise ValueError(f"Unknown paragraph locator: {anchor}")
            text = raw.get("text", "")
            if not isinstance(text, str):
                raise ValueError(f"{op} requires string text")
            if len(text) > 100_000:
                raise ValueError("Inserted paragraph text is too large")
            normalized.append({"op": op, "target": anchor, "text": _norm_text(text)})
            continue

        if op == "delete_paragraph":
            locator = raw.get("target")
            if not isinstance(locator, str) or locator not in locator_index:
                raise ValueError(f"Unknown paragraph locator: {locator}")
            if locator in mutated_targets:
                raise ValueError(f"Duplicate mutation target in one transaction: {locator}")
            mutated_targets.add(locator)
            normalized.append({"op": op, "target": locator})
            continue

        if op in {"move_paragraph_before", "move_paragraph_after"}:
            source = raw.get("target")
            anchor = raw.get("anchor")
            if not isinstance(source, str) or source not in locator_index:
                raise ValueError(f"Unknown paragraph locator: {source}")
            if not isinstance(anchor, str) or anchor not in locator_index:
                raise ValueError(f"Unknown paragraph anchor locator: {anchor}")
            if source == anchor:
                raise ValueError("Move source and anchor must be different paragraphs")
            if locator_index[source]["section"] != locator_index[anchor]["section"]:
                raise ValueError("Cross-section paragraph moves are not supported in P2.1")
            if source in mutated_targets:
                raise ValueError(f"Duplicate mutation target in one transaction: {source}")
            mutated_targets.add(source)
            normalized.append({"op": op, "target": source, "anchor": anchor})
            continue

        raise ValueError(f"Unsupported edit operation: {op}")
    return normalized


def apply_edits_atomic(
    path: Path,
    operations: list[dict],
    *,
    expected_revision: int,
    current_revision: int,
    validator: Callable[[Path], dict] | None = None,
) -> dict:
    if expected_revision != current_revision:
        raise ValueError(f"Stale revision: expected {expected_revision}, current {current_revision}")
    if not operations:
        raise ValueError("At least one edit operation is required")
    if len(operations) > 100:
        raise ValueError("Too many edit operations")

    before_map = build_document_map(path)
    locator_index = _paragraph_index_by_locator(before_map)
    normalized_ops = _normalize_operations(operations, locator_index)

    ops_by_section: dict[str, list[dict]] = {}
    for op in normalized_ops:
        section = locator_index[op["target"]]["section"]
        ops_by_section.setdefault(section, []).append(op)

    fd, tmp_name = tempfile.mkstemp(prefix=path.stem + ".p21-", suffix=".hwpx", dir=str(path.parent))
    os.close(fd)
    tmp_path = Path(tmp_name)
    changes: list[dict] = []
    validation: dict | None = None
    try:
        with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(tmp_path, "w") as target_zip:
            for info in source.infolist():
                payload = source.read(info.filename)
                section_ops = ops_by_section.get(info.filename)
                if section_ops:
                    root = ElementTree.fromstring(payload)
                    original_nodes = _paragraph_nodes(root)
                    locator_to_node = {
                        paragraph["locator"]: original_nodes[int(paragraph["paragraph_index"])]
                        for paragraph in before_map["paragraphs"]
                        if paragraph["section"] == info.filename
                    }
                    for op in section_ops:
                        kind = op["op"]
                        target_node = locator_to_node[op["target"]]
                        if kind == "replace_paragraph_text":
                            before, after = _replace_paragraph_text(target_node, op["text"])
                            changes.append({
                                "op": kind,
                                "target": op["target"],
                                "before": before,
                                "after": after,
                                "before_sha256": hashlib.sha256(before.encode("utf-8")).hexdigest(),
                                "after_sha256": hashlib.sha256(after.encode("utf-8")).hexdigest(),
                            })
                        elif kind in {"insert_paragraph_before", "insert_paragraph_after"}:
                            new_node = _clone_paragraph(target_node, op["text"], root)
                            _insert_relative(root, target_node, new_node, after=kind.endswith("_after"))
                            changes.append({
                                "op": kind,
                                "anchor": op["target"],
                                "inserted_intrinsic_id": _paragraph_intrinsic_id(new_node),
                                "text": op["text"],
                            })
                        elif kind == "delete_paragraph":
                            deleted_text = _paragraph_text(target_node)
                            deleted_id = _paragraph_intrinsic_id(target_node)
                            _delete_node(root, target_node)
                            changes.append({
                                "op": kind,
                                "target": op["target"],
                                "deleted_intrinsic_id": deleted_id,
                                "deleted_text": deleted_text,
                            })
                        elif kind in {"move_paragraph_before", "move_paragraph_after"}:
                            anchor_node = locator_to_node[op["anchor"]]
                            _move_relative(
                                root,
                                target_node,
                                anchor_node,
                                after=kind.endswith("_after"),
                            )
                            changes.append({
                                "op": kind,
                                "target": op["target"],
                                "anchor": op["anchor"],
                            })
                    payload = ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
                target_zip.writestr(info, payload)

        after_map = build_document_map(tmp_path)
        if validator is not None:
            validation = validator(tmp_path)
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise

    after_by_identity = {
        key: item
        for item in after_map["paragraphs"]
        if (key := _identity_key(item)) is not None
    }
    for change in changes:
        inserted_id = change.get("inserted_intrinsic_id")
        if inserted_id is not None:
            section = locator_index[change["anchor"]]["section"]
            inserted = after_by_identity.get((section, str(inserted_id)))
            change["inserted_locator"] = None if inserted is None else inserted["locator"]

    semantic_changed = before_map["semantic_sha256"] != after_map["semantic_sha256"]
    structure_changed = before_map["structure_sha256"] != after_map["structure_sha256"]
    result = {
        "before": {
            "semantic_sha256": before_map["semantic_sha256"],
            "structure_sha256": before_map["structure_sha256"],
            "paragraph_count": before_map["paragraph_count"],
        },
        "after": {
            "semantic_sha256": after_map["semantic_sha256"],
            "structure_sha256": after_map["structure_sha256"],
            "paragraph_count": after_map["paragraph_count"],
        },
        "changes": changes,
        "operation_count": len(normalized_ops),
        "semantic_changed": semantic_changed,
        "structure_changed": structure_changed,
        "no_op": not semantic_changed and not structure_changed,
        "locator_rebinding": _locator_rebinding(before_map, after_map),
    }
    if validation is not None:
        result["validation"] = validation
    return result


def apply_text_edits_atomic(
    path: Path,
    operations: list[dict],
    *,
    expected_revision: int,
    current_revision: int,
    validator: Callable[[Path], dict] | None = None,
) -> dict:
    """Backward-compatible P2 entry point; structural ops are also accepted."""
    return apply_edits_atomic(
        path,
        operations,
        expected_revision=expected_revision,
        current_revision=current_revision,
        validator=validator,
    )
