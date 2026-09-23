from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from lxml import etree


HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HH_NS = "http://www.hancom.co.kr/hwpml/2011/head"
CONFIG_NS = "urn:oasis:names:tc:opendocument:xmlns:config:1.0"

HP = f"{{{HP_NS}}}"
HH = f"{{{HH_NS}}}"
CONFIG = f"{{{CONFIG_NS}}}"

BEGIN = {"insertBegin": "INSERT", "deleteBegin": "DELETE"}
END = {"insertEnd": "INSERT", "deleteEnd": "DELETE"}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _read_package(path: Path) -> tuple[list[zipfile.ZipInfo], dict[str, bytes]]:
    with zipfile.ZipFile(path, "r") as zf:
        bad = zf.testzip()
        if bad:
            raise ValueError(f"HWPX CRC failure: {bad}")
        infos = zf.infolist()
        data = {info.filename: zf.read(info.filename) for info in infos}
    return infos, data


def _write_package(path: Path, infos: list[zipfile.ZipInfo], data: dict[str, bytes]) -> None:
    fd, tmp_name = tempfile.mkstemp(prefix=path.stem + ".p334r2-", suffix=".hwpx", dir=str(path.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        with zipfile.ZipFile(tmp, "w") as zf:
            for info in infos:
                payload = data[info.filename]
                zf.writestr(info, payload)
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise


def _protection_nodes(root: etree._Element) -> list[etree._Element]:
    return [
        node
        for node in root.iter()
        if _local(node.tag) == "config-item-set"
        and node.get("name") == "TrackChangePasswordInfo"
    ]


def _header_state(header_bytes: bytes) -> dict[str, Any]:
    root = etree.fromstring(header_bytes)
    track_changes = root.find(f".//{HH}trackChanges")
    track_authors = root.find(f".//{HH}trackChangeAuthors")
    protection = _protection_nodes(root)
    changes = []
    if track_changes is not None:
        for child in track_changes:
            if _local(child.tag) == "trackChange":
                changes.append({
                    "id": str(child.get("id") or ""),
                    "type": str(child.get("type") or "").upper(),
                })
    return {
        "root": root,
        "changes": changes,
        "authors_count": 0 if track_authors is None else len(track_authors),
        "protected": bool(protection),
        "track_changes_node": track_changes,
        "track_authors_node": track_authors,
    }


def _transform_text_node(node: etree._Element, *, decision: str) -> tuple[int, int]:
    children = list(node)
    marker_children = [child for child in children if _local(child.tag) in {*BEGIN, *END}]
    if not marker_children:
        return 0, 0
    if len(marker_children) != len(children):
        raise ValueError(
            "P3.34-R2 bounded resolution refuses hp:t nodes mixing tracked marks with other inline markup"
        )

    pieces: list[str] = []
    active: tuple[str, str, str] | None = None
    begins = 0
    ends = 0

    def keep_text(kind: str | None) -> bool:
        if kind is None:
            return True
        if decision == "ACCEPT":
            return kind == "INSERT"
        return kind == "DELETE"

    if node.text:
        pieces.append(node.text)

    for child in children:
        local = _local(child.tag)
        if local in BEGIN:
            if active is not None:
                raise ValueError("Nested/overlapping tracked spans are outside P3.34-R2 bounded authority")
            mark_id = str(child.get("Id") or "")
            tc_id = str(child.get("TcId") or "")
            if not mark_id or not tc_id:
                raise ValueError("Tracked begin marker is missing Id/TcId")
            active = (BEGIN[local], mark_id, tc_id)
            begins += 1
        elif local in END:
            if active is None:
                raise ValueError("Tracked end marker has no matching begin")
            kind, mark_id, tc_id = active
            if END[local] != kind:
                raise ValueError("Tracked end marker kind does not match begin")
            if str(child.get("Id") or "") != mark_id or str(child.get("TcId") or "") != tc_id:
                raise ValueError("Tracked end marker Id/TcId does not match begin")
            active = None
            ends += 1
        else:
            raise ValueError(f"Unsupported inline child inside tracked hp:t: {local}")

        tail = child.tail or ""
        current_kind = active[0] if active is not None else None
        # For an end marker, its tail is ordinary text after the span.
        if local in END:
            current_kind = None
        if tail and keep_text(current_kind):
            pieces.append(tail)

    if active is not None:
        raise ValueError("Tracked span is unterminated")

    for child in children:
        node.remove(child)
    node.text = "".join(pieces)
    return begins, ends


def _resolve_sections(data: dict[str, bytes], *, decision: str) -> dict[str, int]:
    begin_count = 0
    end_count = 0
    touched_parts = 0
    for name in sorted(data):
        if not (name.startswith("Contents/section") and name.endswith(".xml")):
            continue
        root = etree.fromstring(data[name])
        part_begins = 0
        part_ends = 0
        for node in root.iter(f"{HP}t"):
            b, e = _transform_text_node(node, decision=decision)
            part_begins += b
            part_ends += e
        if part_begins or part_ends:
            if part_begins != part_ends:
                raise ValueError(f"Tracked marker imbalance in {name}")
            data[name] = etree.tostring(root, encoding="utf-8", xml_declaration=False)
            begin_count += part_begins
            end_count += part_ends
            touched_parts += 1
    return {
        "begin_markers_removed": begin_count,
        "end_markers_removed": end_count,
        "section_parts_touched": touched_parts,
    }


def resolve_all_tracked_changes(path: Path, *, decision: str) -> dict[str, Any]:
    """Resolve every simple P3.22-style tracked text change in *path*.

    Bounded authority:
    - whole-document ACCEPT or REJECT only;
    - Insert/Delete header changes only (Replace is represented by one of each);
    - markers must be simple direct children of hp:t;
    - protected documents are refused.
    """
    decision = str(decision or "").upper()
    if decision not in {"ACCEPT", "REJECT"}:
        raise ValueError("decision must be ACCEPT or REJECT")

    infos, data = _read_package(path)
    if "Contents/header.xml" not in data:
        raise ValueError("HWPX header.xml is missing")

    state = _header_state(data["Contents/header.xml"])
    if state["protected"]:
        raise ValueError(
            "Tracked-change protection is active; P3.34-R2 production authority does not verify passwords"
        )
    if not state["changes"]:
        raise ValueError("Document contains no tracked changes")
    unsupported = [item for item in state["changes"] if item["type"] not in {"INSERT", "DELETE"}]
    if unsupported:
        raise ValueError(f"Unsupported tracked-change types: {unsupported}")

    section_receipt = _resolve_sections(data, decision=decision)
    if section_receipt["begin_markers_removed"] != len(state["changes"]):
        raise ValueError(
            "Tracked body marker count does not match header change count; refusing ambiguous resolution"
        )

    header_root = state["root"]
    for node in (state["track_changes_node"], state["track_authors_node"]):
        if node is not None:
            parent = node.getparent()
            if parent is None:
                raise ValueError("Tracked-change header node has no parent")
            parent.remove(node)
    data["Contents/header.xml"] = etree.tostring(
        header_root, encoding="utf-8", xml_declaration=False
    )

    _write_package(path, infos, data)
    return {
        "ok": True,
        "operation": f"{decision.lower()}_all_tracked_changes",
        "decision": decision,
        "resolved_header_changes": len(state["changes"]),
        "removed_track_change_authors": state["authors_count"],
        **section_receipt,
        "authority": "P3.34-R2_CANDIDATE_UNPROTECTED_ACCEPT_REJECT_ALL",
        "holds": [
            "selective_per_change_resolution",
            "protected_resolution_password_verification",
            "track_change_protection_authoring",
            "mixed_inline_markup_inside_tracked_span",
        ],
    }
