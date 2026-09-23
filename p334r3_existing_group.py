from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from lxml import etree

from p327_diagram_composition import build_diagram_composition_map


HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HC_NS = "http://www.hancom.co.kr/hwpml/2011/core"
HP = f"{{{HP_NS}}}"
HC = f"{{{HC_NS}}}"

ALLOWED_KINDS = {"rect", "ellipse"}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _read_package(path: Path):
    with zipfile.ZipFile(path, "r") as zf:
        bad = zf.testzip()
        if bad:
            raise ValueError(f"HWPX CRC failure: {bad}")
        infos = zf.infolist()
        data = {info.filename: zf.read(info.filename) for info in infos}
    return infos, data


def _write_package(path: Path, infos, data: dict[str, bytes]) -> None:
    fd, tmp_name = tempfile.mkstemp(prefix=path.stem + ".p334r3-", suffix=".hwpx", dir=str(path.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        with zipfile.ZipFile(tmp, "w") as zf:
            for info in infos:
                zf.writestr(info, data[info.filename])
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise


def _int_attr(node, name: str, default: int = 0) -> int:
    raw = node.get(name)
    return default if raw in (None, "") else int(raw)


def _child(node, local: str):
    return node.find(f"{HP}{local}")


def _matrix(node, local: str):
    info = _child(node, "renderingInfo")
    if info is None:
        return None
    return info.find(f"{HC}{local}")


def _identity_only(item: dict, node) -> None:
    rot = item.get("rotation") or {}
    flip = item.get("flip") or {}
    if int(rot.get("angle", "0") or 0) != 0:
        raise ValueError("P3.34-R3 bounded grouping refuses rotated objects")
    if str(flip.get("horizontal", "0")) != "0" or str(flip.get("vertical", "0")) != "0":
        raise ValueError("P3.34-R3 bounded grouping refuses flipped objects")
    for name in ("scaMatrix", "rotMatrix"):
        mat = _matrix(node, name)
        if mat is None:
            continue
        vals = [float(mat.get(k, "0")) for k in ("e1", "e2", "e3", "e4", "e5", "e6")]
        if name == "scaMatrix":
            expected = [1, 0, 0, 0, 1, 0]
        else:
            expected = [1, 0, 0, 0, 1, 0]
        if any(abs(a-b) > 1e-9 for a,b in zip(vals, expected)):
            raise ValueError("P3.34-R3 bounded grouping refuses non-identity child transforms")


def _find_by_instid(root, instid: str):
    matches = [node for node in root.iter() if node.get("instid") == str(instid)]
    if len(matches) != 1:
        raise ValueError(f"Expected one drawing with instid={instid}, found {len(matches)}")
    return matches[0]


def _next_ids(root, count: int) -> list[int]:
    used = set()
    for node in root.iter():
        for key in ("id", "instid"):
            raw = node.get(key)
            if raw and raw.isdigit():
                used.add(int(raw))
    value = max(used or {100000000}) + 1
    out = []
    while len(out) < count:
        if value not in used:
            out.append(value)
            used.add(value)
        value += 1
    return out


def _set_translation(node, x: int, y: int) -> None:
    info = _child(node, "renderingInfo")
    if info is None:
        info = etree.SubElement(node, f"{HP}renderingInfo")
    trans = info.find(f"{HC}transMatrix")
    if trans is None:
        trans = etree.Element(f"{HC}transMatrix")
        info.insert(0, trans)
    for k,v in {"e1":"1","e2":"0","e3":str(x),"e4":"0","e5":"1","e6":str(y)}.items():
        trans.set(k,v)


def _remove_children(node, locals_: set[str]) -> None:
    for child in list(node):
        if _local(child.tag) in locals_:
            node.remove(child)


def _top_level_to_member(node, *, local_x: int, local_y: int) -> etree._Element:
    member = etree.fromstring(etree.tostring(node))
    member.set("id", "0")
    member.set("groupLevel", "1")
    member.set("zOrder", "0")
    member.set("numberingType", "NONE")
    member.set("textWrap", "TOP_AND_BOTTOM")
    member.set("textFlow", "BOTH_SIDES")

    offset = _child(member, "offset")
    if offset is None:
        offset = etree.Element(f"{HP}offset")
        member.insert(0, offset)
    offset.set("x", str(local_x))
    offset.set("y", str(local_y))

    cur = _child(member, "curSz")
    if cur is not None:
        cur.set("width", "0")
        cur.set("height", "0")
    _set_translation(member, local_x, local_y)
    _remove_children(member, {"sz", "pos", "outMargin", "shapeComment"})
    return member


def _member_to_top_level(member, *, new_id: int, x: int, y: int, group_pos: dict, z: int) -> etree._Element:
    node = etree.fromstring(etree.tostring(member))
    node.set("id", str(new_id))
    node.set("groupLevel", "0")
    node.set("zOrder", str(z))
    node.set("numberingType", "PICTURE")
    node.set("textWrap", "SQUARE")
    node.set("textFlow", "BOTH_SIDES")

    offset = _child(node, "offset")
    if offset is None:
        offset = etree.Element(f"{HP}offset")
        node.insert(0, offset)
    offset.set("x", "0")
    offset.set("y", "0")

    org = _child(node, "orgSz")
    if org is None:
        raise ValueError("Group member has no orgSz")
    width = int(org.get("width", "0") or 0)
    height = int(org.get("height", "0") or 0)
    if width <= 0 or height <= 0:
        raise ValueError("Group member has invalid size")

    cur = _child(node, "curSz")
    if cur is not None:
        cur.set("width", "0")
        cur.set("height", "0")
    _set_translation(node, 0, 0)
    _remove_children(node, {"sz", "pos", "outMargin", "shapeComment"})

    sz = etree.Element(f"{HP}sz")
    sz.set("width", str(width)); sz.set("widthRelTo", "ABSOLUTE")
    sz.set("height", str(height)); sz.set("heightRelTo", "ABSOLUTE")
    sz.set("protect", "0")
    node.append(sz)

    pos = etree.Element(f"{HP}pos")
    for key in ("treatAsChar","affectLSpacing","flowWithText","allowOverlap","holdAnchorAndSO",
                "vertRelTo","horzRelTo","vertAlign","horzAlign"):
        if key in group_pos:
            pos.set(key, str(group_pos[key]))
    pos.set("vertOffset", str(y))
    pos.set("horzOffset", str(x))
    node.append(pos)

    margin = etree.Element(f"{HP}outMargin")
    for key in ("left","right","top","bottom"):
        margin.set(key, "0")
    node.append(margin)
    comment = etree.Element(f"{HP}shapeComment")
    comment.text = "사각형입니다." if _local(node.tag) == "rect" else "타원입니다."
    node.append(comment)
    return node


def group_existing_objects(path: Path, drawings: list[str]) -> dict[str, Any]:
    if not isinstance(drawings, list) or len(drawings) != 2:
        raise ValueError("P3.34-R3 bounded group_existing_objects requires exactly two drawings")

    mapped = build_diagram_composition_map(path)
    by_locator = {item["locator"]: item for item in mapped["top_level_objects"]}
    items = [by_locator.get(str(locator)) for locator in drawings]
    if any(item is None for item in items):
        raise ValueError("Unknown top-level drawing locator")
    items = [item for item in items if item is not None]
    if any(item["kind"] not in ALLOWED_KINDS for item in items):
        raise ValueError("P3.34-R3 bounded grouping admits only rect/ellipse")
    anchors = {item.get("anchor_locator") for item in items}
    sections = {item.get("section") for item in items}
    if len(anchors) != 1 or None in anchors or len(sections) != 1:
        raise ValueError("P3.34-R3 grouping requires same anchor and section")
    pos0 = items[0].get("position") or {}
    for item in items:
        pos = item.get("position") or {}
        if item.get("placement") != "floating" or str(pos.get("treatAsChar","")) not in {"0","false","False"}:
            raise ValueError("P3.34-R3 grouping requires floating objects")
        for key in ("horzRelTo","vertRelTo"):
            if pos.get(key) != pos0.get(key):
                raise ValueError("P3.34-R3 grouping requires a shared coordinate frame")

    infos, data = _read_package(path)
    section = next(iter(sections))
    root = etree.fromstring(data[section])
    nodes = []
    boxes = []
    for item in items:
        node = _find_by_instid(root, str(item.get("instid") or item.get("id")))
        _identity_only(item, node)
        pos = item["position"]
        x = int(pos.get("horzOffset","0") or 0)
        y = int(pos.get("vertOffset","0") or 0)
        w = int(item.get("width") or 0); h = int(item.get("height") or 0)
        if w <= 0 or h <= 0:
            raise ValueError("Drawing has invalid geometry")
        nodes.append(node)
        boxes.append((x,y,w,h))

    min_x = min(x for x,_,_,_ in boxes); min_y = min(y for _,y,_,_ in boxes)
    max_x = max(x+w for x,_,w,_ in boxes); max_y = max(y+h for _,y,_,h in boxes)
    width = max_x-min_x; height=max_y-min_y
    new_id,new_instid = _next_ids(root,2)

    container = etree.Element(f"{HP}container")
    attrs = {
        "id":str(new_id),"zOrder":"0","numberingType":"NONE","textWrap":str(items[0].get("text_wrap") or "SQUARE"),
        "textFlow":"BOTH_SIDES","lock":"0","dropcapstyle":"None","href":"","groupLevel":"0","instid":str(new_instid)
    }
    for k,v in attrs.items(): container.set(k,v)
    off=etree.SubElement(container,f"{HP}offset"); off.set("x","0"); off.set("y","0")
    org=etree.SubElement(container,f"{HP}orgSz"); org.set("width",str(width)); org.set("height",str(height))
    cur=etree.SubElement(container,f"{HP}curSz"); cur.set("width","0"); cur.set("height","0")
    flip=etree.SubElement(container,f"{HP}flip"); flip.set("horizontal","0"); flip.set("vertical","0")
    rot=etree.SubElement(container,f"{HP}rotationInfo"); rot.set("angle","0"); rot.set("centerX",str(width//2)); rot.set("centerY",str(height//2)); rot.set("rotateimage","1")
    info=etree.SubElement(container,f"{HP}renderingInfo")
    for tag in ("transMatrix","scaMatrix","rotMatrix"):
        mat=etree.SubElement(info,f"{HC}{tag}")
        for k,v in {"e1":"1","e2":"0","e3":"0","e4":"0","e5":"1","e6":"0"}.items(): mat.set(k,v)

    for node,(x,y,_,_) in zip(nodes,boxes):
        container.append(_top_level_to_member(node,local_x=x-min_x,local_y=y-min_y))

    sz=etree.SubElement(container,f"{HP}sz"); sz.set("width",str(width)); sz.set("height",str(height)); sz.set("widthRelTo","ABSOLUTE"); sz.set("heightRelTo","ABSOLUTE"); sz.set("protect","0")
    pos=etree.SubElement(container,f"{HP}pos")
    for key in ("treatAsChar","affectLSpacing","flowWithText","allowOverlap","holdAnchorAndSO","vertRelTo","vertAlign","horzRelTo","horzAlign"):
        if key in pos0: pos.set(key,str(pos0[key]))
    pos.set("vertOffset",str(min_y)); pos.set("horzOffset",str(min_x))
    margin=etree.SubElement(container,f"{HP}outMargin")
    for key in ("left","right","top","bottom"): margin.set(key,"0")
    etree.SubElement(container,f"{HP}shapeComment")

    first_parent = nodes[0].getparent()
    first_index = first_parent.index(nodes[0])
    first_parent.insert(first_index, container)
    for node in nodes:
        parent=node.getparent()
        if parent is not None:
            parent.remove(node)

    data[section] = etree.tostring(root,encoding="utf-8",xml_declaration=False)
    _write_package(path,infos,data)
    return {
        "ok":True,"operation":"group_existing_objects","group_origin":{"x":min_x,"y":min_y},
        "group_size":{"width":width,"height":height},"member_count":2,
        "authority":"P3.34-R3_CANDIDATE_EXISTING_GROUP_UNGROUP"
    }


def ungroup_existing_objects(path: Path, group: str) -> dict[str, Any]:
    mapped=build_diagram_composition_map(path)
    payload=next((item for item in mapped["groups"] if item["locator"]==str(group)),None)
    if payload is None:
        raise ValueError("Unknown group locator")
    top=next(item for item in mapped["top_level_objects"] if item["locator"]==str(group))
    pos=top.get("position") or {}
    if top.get("placement")!="floating" or str(pos.get("treatAsChar","")) not in {"0","false","False"}:
        raise ValueError("P3.34-R3 ungroup requires a floating group")
    rot=top.get("rotation") or {}; flip=top.get("flip") or {}
    if int(rot.get("angle","0") or 0)!=0 or str(flip.get("horizontal","0"))!="0" or str(flip.get("vertical","0"))!="0":
        raise ValueError("P3.34-R3 ungroup refuses rotated/flipped groups")
    if any(m["kind"] not in ALLOWED_KINDS for m in payload["members"]):
        raise ValueError("P3.34-R3 ungroup admits rect/ellipse members only")

    infos,data=_read_package(path)
    section=top["section"]; root=etree.fromstring(data[section])
    container=_find_by_instid(root,str(top.get("instid") or top.get("id")))
    members=[child for child in list(container) if _local(child.tag) in ALLOWED_KINDS and str(child.get("groupLevel") or "0")=="1"]
    if len(members)!=len(payload["members"]) or not members:
        raise ValueError("Group member structure is ambiguous")
    new_ids=_next_ids(root,len(members))
    gx=int(pos.get("horzOffset","0") or 0); gy=int(pos.get("vertOffset","0") or 0)
    parent=container.getparent(); index=parent.index(container)
    released=[]
    # Native files materialize higher z objects first in XML; insert reverse member order.
    for z,(member,new_id) in enumerate(zip(members,new_ids)):
        off=_child(member,"offset")
        if off is None: raise ValueError("Group member has no offset")
        lx=int(off.get("x","0") or 0); ly=int(off.get("y","0") or 0)
        released.append(_member_to_top_level(member,new_id=new_id,x=gx+lx,y=gy+ly,group_pos=pos,z=z))
    parent.remove(container)
    for node in reversed(released):
        parent.insert(index,node)

    data[section]=etree.tostring(root,encoding="utf-8",xml_declaration=False)
    _write_package(path,infos,data)
    return {
        "ok":True,"operation":"ungroup_existing_objects","released_count":len(released),
        "group_origin":{"x":gx,"y":gy},"authority":"P3.34-R3_CANDIDATE_EXISTING_GROUP_UNGROUP"
    }
