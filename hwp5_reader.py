from __future__ import annotations

import hashlib
import io
import struct
import zlib
from dataclasses import dataclass

import olefile

HWP5_SIGNATURE = b"HWP Document File" + (b"\x00" * 15)
HWPTAG_PARA_HEADER = 0x42
HWPTAG_PARA_TEXT = 0x43
HWPTAG_CTRL_HEADER = 0x47
HWPTAG_LIST_HEADER = 0x48
HWPTAG_TABLE = 0x4D
HWPTAG_SHAPE_COMPONENT = 0x4C
HWPTAG_SHAPE_COMPONENT_PICTURE = 0x55
HWPTAG_EQEDIT = 0x58


class Hwp5ReadError(ValueError):
    pass


@dataclass(frozen=True)
class Hwp5Header:
    version: tuple[int, int, int, int]
    flags: int

    @property
    def compressed(self) -> bool:
        return bool(self.flags & (1 << 0))

    @property
    def password(self) -> bool:
        return bool(self.flags & (1 << 1))

    @property
    def distributable(self) -> bool:
        return bool(self.flags & (1 << 2))

    @property
    def script(self) -> bool:
        return bool(self.flags & (1 << 3))

    @property
    def drm(self) -> bool:
        return bool(self.flags & (1 << 4))

    @property
    def cert_encrypted(self) -> bool:
        return bool(self.flags & (1 << 8))

    def public_flags(self) -> dict:
        return {
            "compressed": self.compressed,
            "password": self.password,
            "distributable": self.distributable,
            "script": self.script,
            "drm": self.drm,
            "xmltemplate_storage": bool(self.flags & (1 << 5)),
            "history": bool(self.flags & (1 << 6)),
            "cert_signed": bool(self.flags & (1 << 7)),
            "cert_encrypted": self.cert_encrypted,
            "cert_signature_extra": bool(self.flags & (1 << 9)),
            "cert_drm": bool(self.flags & (1 << 10)),
            "ccl": bool(self.flags & (1 << 11)),
        }


def _parse_header(raw: bytes) -> Hwp5Header:
    if len(raw) < 40:
        raise Hwp5ReadError("HWP FileHeader is truncated")
    if raw[:32] != HWP5_SIGNATURE:
        raise Hwp5ReadError("Not an HWP 5.x document")
    version_raw = raw[32:36]
    version = (version_raw[3], version_raw[2], version_raw[1], version_raw[0])
    flags = struct.unpack_from("<I", raw, 36)[0]
    return Hwp5Header(version=version, flags=flags)


def _decompress_stream(payload: bytes) -> bytes:
    try:
        return zlib.decompress(payload, -15)
    except zlib.error as exc:
        raise Hwp5ReadError("Compressed HWP stream could not be decompressed") from exc


def _iter_records(payload: bytes):
    offset = 0
    size_total = len(payload)
    while offset + 4 <= size_total:
        header = struct.unpack_from("<I", payload, offset)[0]
        offset += 4
        tag_id = header & 0x3FF
        level = (header >> 10) & 0x3FF
        size = (header >> 20) & 0xFFF
        if size == 0xFFF:
            if offset + 4 > size_total:
                raise Hwp5ReadError("Extended HWP record size is truncated")
            size = struct.unpack_from("<I", payload, offset)[0]
            offset += 4
        end = offset + size
        if end > size_total:
            raise Hwp5ReadError("HWP record payload exceeds its section stream")
        yield tag_id, level, payload[offset:end]
        offset = end


def _clean_para_text(payload: bytes) -> str:
    # HWP PARA_TEXT stores UTF-16LE text mixed with control code units.
    # This first read lane intentionally strips C0 control units instead of
    # interpreting embedded object/control payloads as visible text.
    if len(payload) % 2:
        payload = payload[:-1]
    decoded = payload.decode("utf-16le", errors="replace")
    chars: list[str] = []
    for ch in decoded:
        code = ord(ch)
        if code == 0x0009:
            chars.append("\t")
        elif code in {0x000A, 0x000D}:
            chars.append("\n")
        elif code < 0x0020:
            continue
        elif ch == "\uffff":
            continue
        else:
            chars.append(ch)
    return "".join(chars).replace("\r\n", "\n").replace("\r", "\n").strip("\x00")


def _ctrl_id_text(value: int) -> str:
    return "".join(chr((value >> shift) & 0xFF) for shift in (24, 16, 8, 0))


def _parse_ctrl_header(payload: bytes) -> dict:
    if len(payload) < 4:
        return {
            "ctrl_id": None,
            "fidelity": "inventory",
            "parse_error": "ctrl_header_too_short",
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
        }
    ctrl_value = struct.unpack_from("<I", payload, 0)[0]
    result = {
        "ctrl_id": _ctrl_id_text(ctrl_value),
        "ctrl_id_uint32": ctrl_value,
        "fidelity": "inventory",
        "payload_bytes": len(payload),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
    }
    if len(payload) < 46:
        return result

    attributes = struct.unpack_from("<I", payload, 4)[0]
    vert_offset, horz_offset, width, height, z_order = struct.unpack_from("<iiiiI", payload, 8)
    margins = struct.unpack_from("<HHHH", payload, 28)
    instance_id = struct.unpack_from("<I", payload, 36)[0]
    prevent_page_break = struct.unpack_from("<i", payload, 40)[0]
    description_length = struct.unpack_from("<H", payload, 44)[0]
    description_end = 46 + (2 * description_length)
    description = ""
    if description_end <= len(payload) and description_length:
        description = payload[46:description_end].decode("utf-16le", errors="replace").rstrip("\x00")
    result.update({
        "fidelity": "structural",
        "attributes": attributes,
        "treat_as_char": bool(attributes & 1),
        "vert_rel_to": (attributes >> 3) & 0b11,
        "horz_rel_to": (attributes >> 8) & 0b11,
        "text_wrap": (attributes >> 21) & 0b111,
        "number_category": (attributes >> 26) & 0b111,
        "vertical_offset": vert_offset,
        "horizontal_offset": horz_offset,
        "width": width,
        "height": height,
        "z_order": z_order,
        "outer_margins": {
            "left": margins[0],
            "right": margins[1],
            "top": margins[2],
            "bottom": margins[3],
        },
        "instance_id": instance_id,
        "prevent_page_break": bool(prevent_page_break),
        "description": description,
    })
    return result


def _parse_list_header(payload: bytes) -> dict:
    if len(payload) < 6:
        return {
            "paragraph_count": None,
            "fidelity": "inventory",
            "parse_error": "list_header_too_short",
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
        }
    paragraph_count = struct.unpack_from("<h", payload, 0)[0]
    attributes = struct.unpack_from("<I", payload, 2)[0]
    return {
        "paragraph_count": paragraph_count,
        "attributes": attributes,
        "text_direction": attributes & 0b111,
        "line_break_mode": (attributes >> 3) & 0b11,
        "vertical_alignment": (attributes >> 5) & 0b11,
        "fidelity": "structural",
        "payload_bytes": len(payload),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
    }


def _parse_table_cell_from_list_header(payload: bytes) -> dict | None:
    # Table cell LIST_HEADER = 6-byte paragraph-list header + 26-byte cell properties.
    if len(payload) < 32:
        return None
    column, row, col_span, row_span = struct.unpack_from("<HHHH", payload, 6)
    width, height = struct.unpack_from("<ii", payload, 14)
    margins = struct.unpack_from("<HHHH", payload, 22)
    border_fill_id = struct.unpack_from("<H", payload, 30)[0]
    return {
        "column": column,
        "row": row,
        "col_span": col_span,
        "row_span": row_span,
        "width": width,
        "height": height,
        "margins": {
            "left": margins[0],
            "right": margins[1],
            "top": margins[2],
            "bottom": margins[3],
        },
        "border_fill_id": border_fill_id,
        "fidelity": "structural",
    }


def _parse_picture_record(payload: bytes) -> dict:
    # HWPTAG_SHAPE_COMPONENT_PICTURE body is table 107; picture-info begins at byte 68.
    base = _opaque_object_record("picture", payload)
    if len(payload) < 78:
        base["parse_error"] = "picture_record_too_short"
        return base
    border_color = struct.unpack_from("<I", payload, 0)[0]
    border_thickness = struct.unpack_from("<i", payload, 4)[0]
    border_attributes = struct.unpack_from("<I", payload, 8)[0]
    initial_x = list(struct.unpack_from("<iiii", payload, 12))
    initial_y = list(struct.unpack_from("<iiii", payload, 28))
    crop = struct.unpack_from("<iiii", payload, 44)
    inner_margins = struct.unpack_from("<HHHH", payload, 60)
    brightness = struct.unpack_from("<b", payload, 68)[0]
    contrast = struct.unpack_from("<b", payload, 69)[0]
    effect = payload[70]
    bin_item_id = struct.unpack_from("<H", payload, 71)[0]
    border_transparency = payload[73]
    instance_id = struct.unpack_from("<I", payload, 74)[0]
    base.update({
        "fidelity": "structural",
        "border_color": border_color,
        "border_thickness": border_thickness,
        "border_attributes": border_attributes,
        "initial_x": initial_x,
        "initial_y": initial_y,
        "crop": {
            "left": crop[0],
            "top": crop[1],
            "right": crop[2],
            "bottom": crop[3],
        },
        "inner_margins": {
            "left": inner_margins[0],
            "right": inner_margins[1],
            "top": inner_margins[2],
            "bottom": inner_margins[3],
        },
        "brightness": brightness,
        "contrast": contrast,
        "effect": effect,
        "bin_item_id": bin_item_id,
        "border_transparency": border_transparency,
        "instance_id": instance_id,
    })
    return base


def _parent_indexes(records: list[tuple[int, int, bytes]]) -> list[int | None]:
    parents: list[int | None] = []
    stack: list[int] = []
    for index, (_tag_id, level, _payload) in enumerate(records):
        while stack and records[stack[-1]][1] >= level:
            stack.pop()
        parents.append(stack[-1] if stack else None)
        stack.append(index)
    return parents


def _nearest_ancestor(
    records: list[tuple[int, int, bytes]],
    parents: list[int | None],
    index: int,
    tag_ids: set[int],
) -> int | None:
    current = parents[index]
    while current is not None:
        if records[current][0] in tag_ids:
            return current
        current = parents[current]
    return None


def _bindata_numeric_id(stream_name: str) -> int | None:
    name = stream_name.rsplit("/", 1)[-1]
    if not name.upper().startswith("BIN"):
        return None
    digits = []
    for ch in name[3:]:
        if ch.isdigit():
            digits.append(ch)
        else:
            break
    return int("".join(digits)) if digits else None


def _parse_table_record(payload: bytes) -> dict:
    if len(payload) < 20:
        return {
            "kind": "table",
            "fidelity": "inventory",
            "parse_error": "table_record_too_short",
            "payload_bytes": len(payload),
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
        }
    attributes = struct.unpack_from("<I", payload, 0)[0]
    row_count = struct.unpack_from("<H", payload, 4)[0]
    col_count = struct.unpack_from("<H", payload, 6)[0]
    cell_spacing = struct.unpack_from("<H", payload, 8)[0]
    margins = struct.unpack_from("<HHHH", payload, 10)
    row_sizes_offset = 18
    row_sizes_end = row_sizes_offset + (2 * row_count)
    if row_sizes_end + 2 > len(payload):
        return {
            "kind": "table",
            "fidelity": "inventory",
            "parse_error": "table_record_truncated",
            "row_count": row_count,
            "col_count": col_count,
            "payload_bytes": len(payload),
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
        }
    row_sizes = list(struct.unpack_from(f"<{row_count}H", payload, row_sizes_offset)) if row_count else []
    border_fill_id = struct.unpack_from("<H", payload, row_sizes_end)[0]
    return {
        "kind": "table",
        "fidelity": "structural",
        "attributes": attributes,
        "page_break_mode": attributes & 0b11,
        "repeat_header": bool(attributes & (1 << 2)),
        "row_count": row_count,
        "col_count": col_count,
        "cell_spacing": cell_spacing,
        "margins": {
            "left": margins[0],
            "right": margins[1],
            "top": margins[2],
            "bottom": margins[3],
        },
        "row_sizes": row_sizes,
        "border_fill_id": border_fill_id,
        "payload_bytes": len(payload),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
    }


def _parse_equation_record(payload: bytes) -> dict:
    if len(payload) < 16:
        return {
            "kind": "equation",
            "fidelity": "inventory",
            "parse_error": "equation_record_too_short",
            "payload_bytes": len(payload),
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
        }
    attributes = struct.unpack_from("<I", payload, 0)[0]
    script_length = struct.unpack_from("<H", payload, 4)[0]
    script_end = 6 + (2 * script_length)
    if script_end + 10 > len(payload):
        return {
            "kind": "equation",
            "fidelity": "inventory",
            "parse_error": "equation_record_truncated",
            "script_length": script_length,
            "payload_bytes": len(payload),
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
        }
    script = payload[6:script_end].decode("utf-16le", errors="replace").rstrip("\x00")
    font_size = struct.unpack_from("<I", payload, script_end)[0]
    text_color = struct.unpack_from("<I", payload, script_end + 4)[0]
    baseline = struct.unpack_from("<h", payload, script_end + 8)[0]
    return {
        "kind": "equation",
        "fidelity": "semantic",
        "attributes": attributes,
        "line_mode": bool(attributes & 1),
        "script": script,
        "script_length": script_length,
        "font_size": font_size,
        "text_color": text_color,
        "baseline": baseline,
        "payload_bytes": len(payload),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
    }


def _opaque_object_record(kind: str, payload: bytes, *, fidelity: str = "inventory") -> dict:
    return {
        "kind": kind,
        "fidelity": fidelity,
        "payload_bytes": len(payload),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
    }


def parse_hwp5_bytes(
    data: bytes,
    *,
    max_sections: int = 256,
    max_paragraphs: int = 20000,
    max_text_chars: int = 500000,
) -> dict:
    if len(data) < 512:
        raise Hwp5ReadError("HWP payload is too small")
    try:
        ole = olefile.OleFileIO(io.BytesIO(data))
    except Exception as exc:
        raise Hwp5ReadError("Payload is not a valid OLE/CFB HWP container") from exc

    try:
        if not ole.exists("FileHeader"):
            raise Hwp5ReadError("HWP FileHeader stream is missing")
        header = _parse_header(ole.openstream("FileHeader").read(256))
        if header.password or header.drm or header.cert_encrypted:
            return {
                "ok": True,
                "format": "hwp5",
                "version": ".".join(str(item) for item in header.version),
                "flags": header.public_flags(),
                "readable": False,
                "block_reason": "encrypted_or_drm",
                "paragraphs": [],
                "tables": [],
                "equations": [],
                "objects": [],
                "text": "",
                "warnings": [
                    "Encrypted/DRM HWP content is not decoded by the read-only lane."
                ],
            }

        streams = ["/".join(parts) for parts in ole.listdir(streams=True, storages=False)]
        binary_items = []
        for stream_name in streams:
            if not stream_name.startswith("BinData/"):
                continue
            try:
                binary = ole.openstream(stream_name).read()
            except Exception:
                continue
            binary_items.append({
                "stream": stream_name,
                "bytes": len(binary),
                "sha256": hashlib.sha256(binary).hexdigest(),
            })
        section_names = [
            name for name in streams if name.startswith("BodyText/Section")
        ]
        section_names.sort(
            key=lambda item: int(item.rsplit("Section", 1)[1])
            if item.rsplit("Section", 1)[1].isdigit()
            else 10**9
        )
        if len(section_names) > max_sections:
            raise Hwp5ReadError("HWP section count exceeds the bounded reader limit")

        paragraphs: list[dict] = []
        tables: list[dict] = []
        equations: list[dict] = []
        objects: list[dict] = []
        warnings: list[str] = []
        total_chars = 0
        for section_index, section_name in enumerate(section_names):
            raw = ole.openstream(section_name).read()
            if header.compressed:
                raw = _decompress_stream(raw)
            record_index = 0
            for tag_id, level, record in _iter_records(raw):
                source = {
                    "section_index": section_index,
                    "section_stream": section_name,
                    "record_index": record_index,
                    "record_level": level,
                    "tag_id": tag_id,
                }
                if tag_id == HWPTAG_PARA_TEXT:
                    text = _clean_para_text(record)
                    if text:
                        remaining = max_text_chars - total_chars
                        if remaining <= 0:
                            warnings.append("Text extraction stopped at max_text_chars.")
                            break
                        if len(text) > remaining:
                            text = text[:remaining]
                            warnings.append("Final paragraph was truncated at max_text_chars.")
                        paragraphs.append(
                            {
                                "paragraph_index": len(paragraphs),
                                **source,
                                "text": text,
                            }
                        )
                        total_chars += len(text)
                        if len(paragraphs) >= max_paragraphs:
                            warnings.append("Paragraph extraction stopped at max_paragraphs.")
                            break
                elif tag_id == HWPTAG_TABLE:
                    tables.append({**source, **_parse_table_record(record)})
                elif tag_id == HWPTAG_EQEDIT:
                    equations.append({**source, **_parse_equation_record(record)})
                elif tag_id == HWPTAG_SHAPE_COMPONENT_PICTURE:
                    objects.append({**source, **_opaque_object_record("picture", record)})
                elif tag_id == HWPTAG_SHAPE_COMPONENT:
                    objects.append({**source, **_opaque_object_record("shape", record, fidelity="raw-preserved")})
                record_index += 1
            if len(paragraphs) >= max_paragraphs or total_chars >= max_text_chars:
                break

        preview_text = ""
        if ole.exists("PrvText"):
            preview_raw = ole.openstream("PrvText").read()
            if len(preview_raw) % 2:
                preview_raw = preview_raw[:-1]
            preview_text = preview_raw.decode("utf-16le", errors="replace").strip("\x00")

        return {
            "ok": True,
            "format": "hwp5",
            "version": ".".join(str(item) for item in header.version),
            "flags": header.public_flags(),
            "readable": True,
            "block_reason": None,
            "section_count": len(section_names),
            "paragraph_count": len(paragraphs),
            "text_chars": total_chars,
            "paragraphs": paragraphs,
            "tables": tables,
            "equations": equations,
            "objects": objects,
            "binary_items": binary_items,
            "text": "\n".join(item["text"] for item in paragraphs),
            "preview_text": preview_text[:20000],
            "preview_text_truncated": len(preview_text) > 20000,
            "streams": streams[:512],
            "streams_truncated": len(streams) > 512,
            "warnings": warnings + [
                "HWP 5.x fidelity is graded per object family; table cell content and picture binary linkage are not yet fully reconstructed.",
                "C0 control atoms are stripped rather than interpreted as visible text.",
            ],
            "fidelity": {
                "paragraph_text": "semantic",
                "tables": "structural" if tables else "not-present",
                "equations": "semantic" if equations else "not-present",
                "pictures": "inventory" if any(item["kind"] == "picture" for item in objects) else "not-present",
                "binary_items": "inventory" if binary_items else "not-present",
                "shapes": "raw-preserved" if any(item["kind"] == "shape" for item in objects) else "not-present",
            },
            "authority": "READ_ONLY_LOSS_AWARE",
        }
    finally:
        ole.close()
