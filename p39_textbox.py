from __future__ import annotations

import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path

from lxml import etree

from p2_document import build_document_map

HP_URI = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HC_URI = "http://www.hancom.co.kr/hwpml/2011/core"
HP = f"{{{HP_URI}}}"
HC = f"{{{HC_URI}}}"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _as_bool(value: object) -> str:
    return "1" if bool(value) else "0"


def _bounded_int(value: object, name: str, *, low: int, high: int) -> int:
    result = int(value)
    if result < low or result > high:
        raise ValueError(f"{name} is outside admitted bounds")
    return result


def _paragraph_nodes(root) -> list:
    return [node for node in root.iter() if _local(node.tag) == "p"]


def _first_run(paragraph):
    for child in paragraph:
        if _local(child.tag) == "run":
            return child
    run = etree.Element(f"{HP}run", charPrIDRef="0")
    paragraph.insert(0, run)
    return run


def _matrix(parent, tag: str) -> None:
    etree.SubElement(
        parent,
        f"{HC}{tag}",
        e1="1",
        e2="0",
        e3="0",
        e4="0",
        e5="1",
        e6="0",
    )


def _add_text_paragraph(sublist, text: str, *, para_pr: str, style_id: str, char_pr: str, pid: int) -> None:
    paragraph = etree.SubElement(
        sublist,
        f"{HP}p",
        id=str(pid),
        paraPrIDRef=str(para_pr),
        styleIDRef=str(style_id),
        pageBreak="0",
        columnBreak="0",
        merged="0",
    )
    run = etree.SubElement(paragraph, f"{HP}run", charPrIDRef=str(char_pr))
    etree.SubElement(run, f"{HP}t").text = text


def inject_textbox(
    path: Path,
    *,
    anchor_locator: str,
    paragraphs: list[str],
    width: int,
    height: int,
    treat_as_char: bool,
    horizontal_offset: int = 0,
    vertical_offset: int = 0,
    horz_rel_to: str = "PARA",
    vert_rel_to: str = "PARA",
    z_order: int = 0,
    shape_seed: str = "",
) -> dict:
    if not paragraphs:
        raise ValueError("textbox requires at least one paragraph")
    width = _bounded_int(width, "textbox width", low=1, high=10_000_000)
    height = _bounded_int(height, "textbox height", low=1, high=10_000_000)
    horizontal_offset = _bounded_int(
        horizontal_offset, "textbox horizontal offset", low=-10_000_000, high=10_000_000
    )
    vertical_offset = _bounded_int(
        vertical_offset, "textbox vertical offset", low=-10_000_000, high=10_000_000
    )
    z_order = _bounded_int(z_order, "textbox z-order", low=-1_000_000, high=1_000_000)

    mapped = build_document_map(path)
    target = next(
        (item for item in mapped["paragraphs"] if item["locator"] == str(anchor_locator)),
        None,
    )
    if target is None:
        raise ValueError("textbox anchor locator does not resolve")
    section_name = str(target["section"])
    paragraph_index = int(target["paragraph_index"])

    seed = (
        f"{shape_seed}\0{anchor_locator}\0{width}\0{height}\0"
        + "\n".join(str(item) for item in paragraphs)
    )
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    shape_id = 100_000_000 + (int.from_bytes(digest[:4], "big") % 1_900_000_000)
    inst_id = 100_000_000 + (int.from_bytes(digest[4:8], "big") % 1_900_000_000)

    fd, tmp_name = tempfile.mkstemp(prefix=path.stem + ".p39-tbox-", suffix=".hwpx", dir=str(path.parent))
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(tmp_path, "w") as target_zip:
            for info in source.infolist():
                payload = source.read(info.filename)
                if info.filename == section_name:
                    root = etree.fromstring(payload)
                    para_nodes = _paragraph_nodes(root)
                    if paragraph_index < 0 or paragraph_index >= len(para_nodes):
                        raise ValueError("textbox anchor paragraph index is stale")
                    host = para_nodes[paragraph_index]
                    host_run = _first_run(host)
                    para_pr = host.get("paraPrIDRef") or "0"
                    style_id = host.get("styleIDRef") or "0"
                    char_pr = host_run.get("charPrIDRef") or "0"

                    rect = etree.SubElement(
                        host_run,
                        f"{HP}rect",
                        id=str(shape_id),
                        zOrder=str(z_order),
                        numberingType="NONE",
                        textWrap="TOP_AND_BOTTOM" if treat_as_char else "IN_FRONT_OF_TEXT",
                        textFlow="BOTH_SIDES",
                        lock="0",
                        dropcapstyle="None",
                        href="",
                        groupLevel="0",
                        instid=str(inst_id),
                        ratio="0",
                    )
                    etree.SubElement(
                        rect, f"{HP}sz",
                        width=str(width), widthRelTo="ABSOLUTE",
                        height=str(height), heightRelTo="ABSOLUTE", protect="0",
                    )
                    etree.SubElement(
                        rect, f"{HP}pos",
                        treatAsChar=_as_bool(treat_as_char),
                        affectLSpacing="0",
                        flowWithText="1" if treat_as_char else "0",
                        allowOverlap="0" if treat_as_char else "1",
                        holdAnchorAndSO="0",
                        vertRelTo=str(vert_rel_to),
                        horzRelTo=str(horz_rel_to),
                        vertAlign="TOP",
                        horzAlign="LEFT",
                        vertOffset=str(vertical_offset),
                        horzOffset=str(horizontal_offset),
                    )
                    etree.SubElement(rect, f"{HP}outMargin", left="0", right="0", top="0", bottom="0")
                    etree.SubElement(rect, f"{HP}offset", x="0", y="0")
                    etree.SubElement(rect, f"{HP}orgSz", width=str(width), height=str(height))
                    etree.SubElement(rect, f"{HP}curSz", width=str(width), height=str(height))
                    etree.SubElement(rect, f"{HP}flip", horizontal="0", vertical="0")
                    etree.SubElement(
                        rect, f"{HP}rotationInfo", angle="0",
                        centerX=str(width // 2), centerY=str(height // 2), rotateimage="1",
                    )
                    rendering = etree.SubElement(rect, f"{HP}renderingInfo")
                    _matrix(rendering, "transMatrix")
                    _matrix(rendering, "scaMatrix")
                    _matrix(rendering, "rotMatrix")
                    etree.SubElement(
                        rect, f"{HP}lineShape",
                        color="#000000", width="33", style="SOLID", endCap="FLAT",
                        headStyle="NORMAL", tailStyle="NORMAL", headfill="1", tailfill="1",
                        headSz="SMALL_SMALL", tailSz="SMALL_SMALL", outlineStyle="NORMAL", alpha="0",
                    )
                    fill = etree.SubElement(rect, f"{HC}fillBrush")
                    etree.SubElement(fill, f"{HC}winBrush", faceColor="#FFFFFF", hatchColor="#000000", alpha="0")
                    etree.SubElement(
                        rect, f"{HP}shadow",
                        type="NONE", color="#B2B2B2", offsetX="0", offsetY="0", alpha="0",
                    )
                    draw = etree.SubElement(
                        rect, f"{HP}drawText", lastWidth=str(width), name="", editable="0"
                    )
                    sublist = etree.SubElement(
                        draw, f"{HP}subList",
                        id="", textDirection="HORIZONTAL", lineWrap="BREAK", vertAlign="TOP",
                        linkListIDRef="0", linkListNextIDRef="0",
                        textWidth="0", textHeight="0", hasTextRef="0", hasNumRef="0",
                    )
                    for idx, text in enumerate(paragraphs):
                        _add_text_paragraph(
                            sublist,
                            str(text),
                            para_pr=str(para_pr),
                            style_id=str(style_id),
                            char_pr=str(char_pr),
                            pid=shape_id + idx + 1,
                        )
                    etree.SubElement(draw, f"{HP}textMargin", left="283", right="283", top="283", bottom="283")
                    etree.SubElement(rect, f"{HP}pt0", x="0", y="0")
                    etree.SubElement(rect, f"{HP}pt1", x=str(width), y="0")
                    etree.SubElement(rect, f"{HP}pt2", x=str(width), y=str(height))
                    etree.SubElement(rect, f"{HP}pt3", x="0", y=str(height))
                    payload = etree.tostring(
                        root, encoding="UTF-8", xml_declaration=True, standalone=True
                    )
                target_zip.writestr(info, payload)
        os.replace(tmp_path, path)
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass

    return {
        "shape_id": str(shape_id),
        "instid": str(inst_id),
        "anchor_locator": anchor_locator,
        "paragraph_count": len(paragraphs),
        "width": width,
        "height": height,
        "treat_as_char": bool(treat_as_char),
        "horizontal_offset": horizontal_offset,
        "vertical_offset": vertical_offset,
        "horz_rel_to": str(horz_rel_to),
        "vert_rel_to": str(vert_rel_to),
        "z_order": z_order,
    }


def build_textbox_map(path: Path) -> dict:
    document_map = build_document_map(path)
    paragraph_by_position = {
        (item["section"], int(item["paragraph_index"])): item
        for item in document_map["paragraphs"]
    }
    boxes: list[dict] = []
    with zipfile.ZipFile(path, "r") as archive:
        for section_index, section in enumerate(document_map["sections"]):
            section_name = section["section"]
            root = etree.fromstring(archive.read(section_name))
            paras = _paragraph_nodes(root)
            para_ord = {id(node): index for index, node in enumerate(paras)}
            for rect in root.iter(f"{HP}rect"):
                draw = rect.find(f"{HP}drawText")
                if draw is None:
                    continue
                owner = rect.getparent()
                while owner is not None and _local(owner.tag) != "p":
                    owner = owner.getparent()
                owner_index = para_ord.get(id(owner), -1)
                owner_map = paragraph_by_position.get((section_name, owner_index))
                sz = rect.find(f"{HP}sz")
                pos = rect.find(f"{HP}pos")
                texts: list[str] = []
                for paragraph in draw.iter(f"{HP}p"):
                    parts = [
                        node.text or ""
                        for node in paragraph.iter(f"{HP}t")
                    ]
                    texts.append("".join(parts))
                boxes.append({
                    "textbox_index": len(boxes),
                    "section_index": section_index,
                    "section": section_name,
                    "anchor_paragraph_index": owner_index,
                    "anchor_locator": None if owner_map is None else owner_map["locator"],
                    "shape_id": rect.get("id"),
                    "instid": rect.get("instid"),
                    "width": None if sz is None else int(sz.get("width", "0") or 0),
                    "height": None if sz is None else int(sz.get("height", "0") or 0),
                    "position": None if pos is None else dict(pos.attrib),
                    "z_order": rect.get("zOrder"),
                    "paragraphs": texts,
                    "text": "\n".join(texts),
                })
    seed = [
        {
            "anchor_locator": item["anchor_locator"],
            "width": item["width"],
            "height": item["height"],
            "position": item["position"],
            "z_order": item["z_order"],
            "text": item["text"],
        }
        for item in boxes
    ]
    return {
        "textboxes": boxes,
        "textbox_count": len(boxes),
        "textbox_geometry_sha256": hashlib.sha256(
            json.dumps(seed, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    }
