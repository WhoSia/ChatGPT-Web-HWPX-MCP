from __future__ import annotations

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


def _replace_paragraph_text(root: ElementTree.Element, target_index: int, new_text: str) -> tuple[str, str]:
    current = -1
    for node in root.iter():
        if _local(node.tag) != "p":
            continue
        current += 1
        if current != target_index:
            continue
        before = _paragraph_text(node)
        text_nodes = [elem for elem in node.iter() if _local(elem.tag) == "t"]
        if not text_nodes:
            raise ValueError("Target paragraph has no editable text node")
        text_nodes[0].text = new_text
        for elem in text_nodes[1:]:
            elem.text = ""
        return before, new_text
    raise ValueError("Target paragraph no longer exists")


def apply_text_edits_atomic(
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
    normalized_ops: list[dict] = []
    seen: set[str] = set()
    for raw in operations:
        if not isinstance(raw, dict):
            raise ValueError("Each edit operation must be an object")
        op = raw.get("op")
        locator = raw.get("target")
        if op != "replace_paragraph_text":
            raise ValueError(f"Unsupported edit operation: {op}")
        if not isinstance(locator, str) or locator not in locator_index:
            raise ValueError(f"Unknown paragraph locator: {locator}")
        if locator in seen:
            raise ValueError(f"Duplicate target in one transaction: {locator}")
        seen.add(locator)
        text = raw.get("text")
        if not isinstance(text, str):
            raise ValueError("replace_paragraph_text requires string text")
        if len(text) > 100_000:
            raise ValueError("Replacement text is too large")
        normalized_ops.append({"op": op, "target": locator, "text": _norm_text(text)})

    edits_by_section: dict[str, list[tuple[dict, dict]]] = {}
    for op in normalized_ops:
        target = locator_index[op["target"]]
        edits_by_section.setdefault(target["section"], []).append((op, target))

    fd, tmp_name = tempfile.mkstemp(prefix=path.stem + ".p2-", suffix=".hwpx", dir=str(path.parent))
    os.close(fd)
    tmp_path = Path(tmp_name)
    semantic_changes: list[dict] = []
    validation: dict | None = None
    try:
        with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(tmp_path, "w") as target_zip:
            for info in source.infolist():
                payload = source.read(info.filename)
                section_edits = edits_by_section.get(info.filename)
                if section_edits:
                    root = ElementTree.fromstring(payload)
                    for op, target in section_edits:
                        before, after = _replace_paragraph_text(root, int(target["paragraph_index"]), op["text"])
                        semantic_changes.append(
                            {
                                "target": op["target"],
                                "kind": "paragraph_text",
                                "before": before,
                                "after": after,
                                "before_sha256": hashlib.sha256(before.encode("utf-8")).hexdigest(),
                                "after_sha256": hashlib.sha256(after.encode("utf-8")).hexdigest(),
                            }
                        )
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

    no_op = before_map["semantic_sha256"] == after_map["semantic_sha256"]
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
        "changes": semantic_changes,
        "operation_count": len(normalized_ops),
        "no_op": no_op,
    }
    if validation is not None:
        result["validation"] = validation
    return result
