from __future__ import annotations

import hashlib
import io
import struct
import zlib
from dataclasses import dataclass

import olefile
from PIL import Image

HWP5_SIGNATURE = b"HWP Document File" + (b"\x00" * 15)
HWPTAG_ID_MAPPINGS = 0x11
HWPTAG_BIN_DATA = 0x12
HWPTAG_FACE_NAME = 0x13
HWPTAG_CHAR_SHAPE = 0x15
HWPTAG_PARA_SHAPE = 0x19
HWPTAG_STYLE = 0x1A
HWPTAG_PARA_HEADER = 0x42
HWPTAG_PARA_TEXT = 0x43
HWPTAG_PARA_CHAR_SHAPE = 0x44
HWPTAG_CTRL_HEADER = 0x47
HWPTAG_LIST_HEADER = 0x48
HWPTAG_TABLE = 0x4D
HWPTAG_SHAPE_COMPONENT = 0x4C
HWPTAG_SHAPE_COMPONENT_LINE = 0x4E
HWPTAG_SHAPE_COMPONENT_RECTANGLE = 0x4F
HWPTAG_SHAPE_COMPONENT_ELLIPSE = 0x50
HWPTAG_SHAPE_COMPONENT_ARC = 0x51
HWPTAG_SHAPE_COMPONENT_POLYGON = 0x52
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


_HWP8_CONTROL_CODES = set(range(1, 10)) | {11, 12} | set(range(14, 24))


def _scan_para_text(payload: bytes) -> dict:
    """Decode HWP PARA_TEXT while preserving source-WCHAR to visible-text coordinates."""
    if len(payload) % 2:
        payload = payload[:-1]
    units = [
        struct.unpack_from("<H", payload, offset)[0]
        for offset in range(0, len(payload), 2)
    ]
    chars: list[str] = []
    # visible_offsets[n] = visible character offset after consuming n source WCHARs.
    visible_offsets = [0] * (len(units) + 1)
    controls: list[dict] = []
    source_index = 0
    visible_index = 0

    while source_index < len(units):
        visible_offsets[source_index] = visible_index
        code = units[source_index]

        if code in _HWP8_CONTROL_CODES:
            # Valid HWP extended controls occupy exactly 8 WCHARs. A truncated
            # synthetic/corrupt tail is treated as one opaque control so we do
            # not accidentally consume following visible text.
            width = 8 if (len(units) - source_index) >= 8 else 1
            if code == 9:
                chars.append("\t")
                visible_index += 1
            controls.append({
                "source_position": source_index,
                "code": code,
                "source_width": width,
                "visible_width": 1 if code == 9 else 0,
            })
            for skipped in range(1, width + 1):
                if source_index + skipped <= len(units):
                    visible_offsets[source_index + skipped] = visible_index
            source_index += width
            continue

        if code == 10:  # line break
            chars.append("\n")
            visible_index += 1
        elif code == 13:
            # PARA_TEXT already belongs to one paragraph; paragraph-end is
            # structural and must not become visible paragraph text.
            pass
        elif code == 24:
            chars.append("-")
            visible_index += 1
        elif code in {30, 31}:
            chars.append(" ")
            visible_index += 1
        elif code in {0, 25, 26, 27, 28, 29}:
            pass
        elif code < 0x20:
            # Defensive fail-closed handling for currently unknown 1-WCHAR controls.
            controls.append({
                "source_position": source_index,
                "code": code,
                "source_width": 1,
                "visible_width": 0,
            })
        elif 0xD800 <= code <= 0xDBFF:
            if source_index + 1 < len(units) and 0xDC00 <= units[source_index + 1] <= 0xDFFF:
                low = units[source_index + 1]
                scalar = 0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00)
                chars.append(chr(scalar))
                visible_index += 1
                source_index += 1
                visible_offsets[source_index] = visible_index
            else:
                chars.append("\uFFFD")
                visible_index += 1
        elif 0xDC00 <= code <= 0xDFFF:
            chars.append("\uFFFD")
            visible_index += 1
        elif code != 0xFFFF:
            chars.append(chr(code))
            visible_index += 1

        source_index += 1
        visible_offsets[source_index] = visible_index

    return {
        "text": "".join(chars).replace("\r\n", "\n").replace("\r", "\n").strip("\x00"),
        "visible_offsets": visible_offsets,
        "controls": controls,
        "source_wchar_count": len(units),
        "visible_char_count": visible_index,
    }


def _clean_para_text(payload: bytes) -> str:
    return _scan_para_text(payload)["text"]


def _parse_para_header(payload: bytes) -> dict:
    if len(payload) < 22:
        return {
            "fidelity": "inventory",
            "parse_error": "para_header_too_short",
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
        }
    char_count, control_mask = struct.unpack_from("<II", payload, 0)
    para_shape_id = struct.unpack_from("<H", payload, 8)[0]
    para_style_id = payload[10]
    break_type = payload[11]
    char_shape_count, range_tag_count, line_seg_count = struct.unpack_from("<HHH", payload, 12)
    instance_id = struct.unpack_from("<I", payload, 18)[0]
    return {
        "fidelity": "structural",
        "char_count": char_count,
        "control_mask": control_mask,
        "para_shape_id": para_shape_id,
        "para_style_id": para_style_id,
        "break_type": break_type,
        "char_shape_count": char_shape_count,
        "range_tag_count": range_tag_count,
        "line_seg_count": line_seg_count,
        "instance_id": instance_id,
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
    }


def _parse_para_char_shapes(payload: bytes) -> list[dict]:
    if len(payload) % 8:
        raise Hwp5ReadError("PARA_CHAR_SHAPE payload is not aligned to 8-byte entries")
    result = []
    for offset in range(0, len(payload), 8):
        position, char_shape_id = struct.unpack_from("<II", payload, offset)
        result.append({
            "source_position": position,
            "char_shape_id": char_shape_id,
        })
    return result


HWP_FONT_LANGUAGES = ("hangul", "latin", "hanja", "japanese", "other", "symbol", "user")


def _parse_id_mappings(payload: bytes) -> dict:
    count = min(len(payload) // 4, 18)
    values = list(struct.unpack_from(f"<{count}i", payload, 0)) if count else []
    while len(values) < 18:
        values.append(0)
    return {
        "binary_data": max(0, values[0]),
        "font_counts": {
            language: max(0, values[index + 1])
            for index, language in enumerate(HWP_FONT_LANGUAGES)
        },
        "border_fill": max(0, values[8]),
        "char_shape": max(0, values[9]),
        "tab_def": max(0, values[10]),
        "numbering": max(0, values[11]),
        "bullet": max(0, values[12]),
        "para_shape": max(0, values[13]),
        "style": max(0, values[14]),
        "memo_shape": max(0, values[15]),
        "track_change": max(0, values[16]),
        "track_change_author": max(0, values[17]),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
    }


def _parse_face_name(payload: bytes) -> dict:
    if len(payload) < 3:
        return {
            "fidelity": "inventory",
            "parse_error": "face_name_too_short",
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
        }
    attributes = payload[0]
    name_len = struct.unpack_from("<H", payload, 1)[0]
    name_end = 3 + (2 * name_len)
    if name_end > len(payload):
        return {
            "fidelity": "inventory",
            "parse_error": "face_name_truncated",
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
        }
    face = payload[3:name_end].decode("utf-16le", errors="replace").rstrip("\x00")
    result = {
        "fidelity": "semantic",
        "attributes": attributes,
        "face": face,
        "has_alternative": bool(attributes & 0x80),
        "has_type_info": bool(attributes & 0x40),
        "has_default": bool(attributes & 0x20),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
    }
    offset = name_end
    if result["has_alternative"] and offset + 3 <= len(payload):
        result["alternative_type"] = payload[offset]
        alt_len = struct.unpack_from("<H", payload, offset + 1)[0]
        offset += 3
        alt_end = offset + (2 * alt_len)
        if alt_end <= len(payload):
            result["alternative_face"] = payload[offset:alt_end].decode(
                "utf-16le", errors="replace"
            ).rstrip("\x00")
            offset = alt_end
    if result["has_type_info"] and offset + 10 <= len(payload):
        result["type_info"] = list(payload[offset:offset + 10])
        offset += 10
    if result["has_default"] and offset + 2 <= len(payload):
        default_len = struct.unpack_from("<H", payload, offset)[0]
        offset += 2
        default_end = offset + (2 * default_len)
        if default_end <= len(payload):
            result["default_face"] = payload[offset:default_end].decode(
                "utf-16le", errors="replace"
            ).rstrip("\x00")
    return result


def _parse_docinfo_para_shape(payload: bytes, index: int) -> dict:
    # The first 34 bytes are stable across HWP5 revisions and carry the
    # paragraph semantics needed for P3.8 canonicalization.
    if len(payload) < 34:
        return {
            "para_shape_id": index,
            "fidelity": "inventory",
            "parse_error": "para_shape_record_too_short",
            "payload_bytes": len(payload),
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
        }
    attributes = struct.unpack_from("<I", payload, 0)[0]
    left, right, indent, before, after, line_spacing = struct.unpack_from(
        "<iiiiii", payload, 4
    )
    tab_id, numbering_id, border_fill_id = struct.unpack_from("<HHH", payload, 28)
    alignment_code = (attributes >> 2) & 0b111
    alignment = {
        0: "JUSTIFY",
        1: "LEFT",
        2: "RIGHT",
        3: "CENTER",
        4: "DISTRIBUTE",
        5: "DISTRIBUTE_SPACE",
    }.get(alignment_code, "UNKNOWN")
    return {
        "para_shape_id": index,
        "fidelity": "semantic",
        "attributes": attributes,
        "alignment_code": alignment_code,
        "alignment": alignment,
        "left_margin_hwpunit": left,
        "right_margin_hwpunit": right,
        "indent_hwpunit": indent,
        "spacing_before_hwpunit": before,
        "spacing_after_hwpunit": after,
        "line_spacing": line_spacing,
        "tab_def_id": tab_id,
        "numbering_id": numbering_id,
        "border_fill_id": border_fill_id,
        "payload_bytes": len(payload),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
    }


def _read_hwp_string(payload: bytes, offset: int) -> tuple[str, int]:
    if offset + 2 > len(payload):
        raise Hwp5ReadError("HWP string length is truncated")
    length = struct.unpack_from("<H", payload, offset)[0]
    offset += 2
    end = offset + (2 * length)
    if end > len(payload):
        raise Hwp5ReadError("HWP string payload is truncated")
    return payload[offset:end].decode("utf-16le", errors="replace").rstrip("\x00"), end


def _parse_docinfo_style(payload: bytes, index: int) -> dict:
    try:
        local_name, offset = _read_hwp_string(payload, 0)
        english_name, offset = _read_hwp_string(payload, offset)
    except Hwp5ReadError as exc:
        return {
            "style_id": index,
            "fidelity": "inventory",
            "parse_error": str(exc),
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
        }
    if offset + 8 > len(payload):
        return {
            "style_id": index,
            "fidelity": "inventory",
            "local_name": local_name,
            "english_name": english_name,
            "parse_error": "style_record_too_short",
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
        }
    style_type = payload[offset]
    next_style_id = payload[offset + 1]
    lang_id = struct.unpack_from("<h", payload, offset + 2)[0]
    para_shape_id = struct.unpack_from("<H", payload, offset + 4)[0]
    char_shape_id = struct.unpack_from("<H", payload, offset + 6)[0]
    trailing = (
        struct.unpack_from("<H", payload, offset + 8)[0]
        if offset + 10 <= len(payload)
        else None
    )
    return {
        "style_id": index,
        "fidelity": "semantic",
        "local_name": local_name,
        "english_name": english_name,
        "style_type": style_type,
        "next_style_id": next_style_id,
        "lang_id": lang_id,
        "para_shape_id": para_shape_id,
        "char_shape_id": char_shape_id,
        "trailing": trailing,
        "payload_bytes": len(payload),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
    }


def _resolve_char_shape_faces(
    char_shape: dict,
    face_names: dict[str, list[dict]],
) -> dict:
    result = dict(char_shape)
    resolved: dict[str, str | None] = {}
    face_ids = list(result.get("face_ids") or [])
    for index, language in enumerate(HWP_FONT_LANGUAGES):
        face_id = int(face_ids[index]) if index < len(face_ids) else -1
        faces = face_names.get(language, [])
        resolved[language] = (
            str(faces[face_id].get("face"))
            if 0 <= face_id < len(faces) and faces[face_id].get("face")
            else None
        )
    result["font_faces"] = resolved
    result["primary_font_face"] = (
        resolved.get("hangul")
        or resolved.get("latin")
        or next((value for value in resolved.values() if value), None)
    )
    result["font_resolution_fidelity"] = (
        "semantic" if result["primary_font_face"] else "id-only"
    )
    return result


def _parse_docinfo_char_shape(payload: bytes, index: int) -> dict:
    if len(payload) < 70:
        return {
            "char_shape_id": index,
            "fidelity": "inventory",
            "parse_error": "char_shape_record_too_short",
            "payload_bytes": len(payload),
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
        }
    face_ids = list(struct.unpack_from("<7H", payload, 0))
    ratios = list(payload[14:21])
    spacing = list(struct.unpack_from("<7b", payload, 21))
    relative_sizes = list(payload[28:35])
    offsets = list(struct.unpack_from("<7b", payload, 35))
    height = struct.unpack_from("<I", payload, 42)[0]
    attributes = struct.unpack_from("<I", payload, 46)[0]
    shadow_x = struct.unpack_from("<b", payload, 50)[0]
    shadow_y = struct.unpack_from("<b", payload, 51)[0]
    text_color, underline_color, shade_color, shadow_color = struct.unpack_from("<IIII", payload, 52)
    border_fill_id = struct.unpack_from("<H", payload, 68)[0]
    result = {
        "char_shape_id": index,
        "fidelity": "semantic",
        "face_ids": face_ids,
        "ratios": ratios,
        "spacing": spacing,
        "relative_sizes": relative_sizes,
        "offsets": offsets,
        "height": height,
        "attributes": attributes,
        "italic": bool(attributes & (1 << 0)),
        "bold": bool(attributes & (1 << 1)),
        "underline_type": (attributes >> 2) & 0b11,
        "outline_type": (attributes >> 8) & 0b111,
        "shadow_type": (attributes >> 11) & 0b11,
        "emboss": bool(attributes & (1 << 13)),
        "engrave": bool(attributes & (1 << 14)),
        "superscript": bool(attributes & (1 << 15)),
        "subscript": bool(attributes & (1 << 16)),
        "shadow_offset_x": shadow_x,
        "shadow_offset_y": shadow_y,
        "text_color": text_color,
        "underline_color": underline_color,
        "shade_color": shade_color,
        "shadow_color": shadow_color,
        "border_fill_id": border_fill_id,
        "payload_bytes": len(payload),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
    }
    if len(payload) >= 74:
        result["strikeout_color"] = struct.unpack_from("<I", payload, 70)[0]
    return result


def _flow_kind_for_control(ctrl_id: str | None) -> str:
    return {
        "head": "header",
        "foot": "footer",
        "fn  ": "footnote",
        "en  ": "endnote",
        "gso ": "object-text",
    }.get(str(ctrl_id or ""), "body")


def _build_run_receipts(
    text: str,
    header: dict,
    changes: list[dict],
    char_shapes: list[dict],
    scan: dict | None = None,
) -> dict:
    normalized = sorted(changes, key=lambda item: int(item["source_position"]))
    if not normalized:
        return {
            "runs": [],
            "visible_span_fidelity": "none",
            "source_coordinate_authority": "none",
        }
    offsets = None if scan is None else scan.get("visible_offsets")
    if offsets is None and not int(header.get("control_mask", 0) or 0):
        # In a control-free paragraph, PARA_CHAR_SHAPE source WCHAR offsets
        # coincide with visible text coordinates.
        offsets = list(range(len(text) + 1))
    source_limit = int(
        header.get(
            "char_count",
            0 if scan is None else scan.get("source_wchar_count", len(text)),
        )
        or (0 if scan is None else scan.get("source_wchar_count", len(text)))
        or len(text)
    )

    def to_visible(source_position: int) -> int | None:
        if offsets is None:
            return None
        pos = max(0, min(int(source_position), len(offsets) - 1))
        return max(0, min(int(offsets[pos]), len(text)))

    runs = []
    for index, change in enumerate(normalized):
        start = int(change["source_position"])
        end = (
            int(normalized[index + 1]["source_position"])
            if index + 1 < len(normalized)
            else source_limit
        )
        shape_id = int(change["char_shape_id"])
        shape = char_shapes[shape_id] if 0 <= shape_id < len(char_shapes) else None
        item = {
            "run_index": index,
            "source_start": start,
            "source_end": end,
            "char_shape_id": shape_id,
            "char_shape": shape,
            "fidelity": "semantic" if shape and shape.get("fidelity") == "semantic" else "structural",
        }
        visible_start = to_visible(start)
        visible_end = to_visible(end)
        if visible_start is not None and visible_end is not None:
            visible_end = max(visible_start, visible_end)
            item.update({
                "visible_start": visible_start,
                "visible_end": visible_end,
                "text": text[visible_start:visible_end],
                "visible_span_certified": True,
            })
        else:
            item["visible_span_certified"] = False
        runs.append(item)

    certified = all(item.get("visible_span_certified") for item in runs)
    return {
        "runs": runs,
        "visible_span_fidelity": "semantic" if certified else "source-coordinate-only",
        "source_coordinate_authority": "structural",
    }


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
    ctrl_id = result["ctrl_id"]
    if ctrl_id in {"head", "foot"}:
        if len(payload) < 18:
            result["parse_error"] = "header_footer_ctrl_truncated"
            return result
        attributes = struct.unpack_from("<I", payload, 4)[0]
        text_width, text_height = struct.unpack_from("<ii", payload, 8)
        page_code = attributes & 0b11
        result.update({
            "fidelity": "semantic",
            "attributes": attributes,
            "apply_page_type": {0: "BOTH", 1: "EVEN", 2: "ODD"}.get(
                page_code, "UNKNOWN"
            ),
            "text_width": text_width,
            "text_height": text_height,
            "text_reference_flags": payload[16],
            "number_reference_flags": payload[17],
        })
        return result
    if ctrl_id in {"fn  ", "en  "}:
        # The HWP5 spec defines no note-specific attributes beyond its paragraph
        # list; implementations serialize eight bytes for compatibility.
        result.update({
            "fidelity": "structural",
            "note_payload_bytes": max(0, len(payload) - 4),
        })
        return result
    if len(payload) < 46:
        return result

    attributes = struct.unpack_from("<I", payload, 4)[0]
    vert_offset, horz_offset, width, height, z_order = struct.unpack_from("<iiiii", payload, 8)
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


def _parse_header_footer_from_list_header(payload: bytes) -> dict | None:
    # Header/footer LIST_HEADER = 6-byte paragraph-list header + 14-byte family data.
    if len(payload) < 20:
        return None
    attributes = struct.unpack_from("<I", payload, 6)[0]
    text_width, text_height = struct.unpack_from("<ii", payload, 10)
    page_code = attributes & 0b11
    return {
        "fidelity": "semantic",
        "attributes": attributes,
        "apply_page_type": {0: "BOTH", 1: "EVEN", 2: "ODD"}.get(
            page_code, "UNKNOWN"
        ),
        "text_width": text_width,
        "text_height": text_height,
        "text_reference_flags": payload[18],
        "number_reference_flags": payload[19],
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


def _parse_bindata_record(payload: bytes) -> dict:
    if len(payload) < 2:
        return {
            "fidelity": "inventory",
            "parse_error": "bindata_record_too_short",
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
        }
    attributes = struct.unpack_from("<H", payload, 0)[0]
    data_type = attributes & 0x000F
    compression = attributes & 0x0030
    status = attributes & 0x0300
    result = {
        "attributes": attributes,
        "data_type": data_type,
        "compression": compression,
        "status": status,
        "fidelity": "structural",
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
    }
    offset = 2
    if data_type == 0:  # LINK
        if offset + 2 > len(payload):
            return {**result, "parse_error": "bindata_link_truncated"}
        len1 = struct.unpack_from("<H", payload, offset)[0]
        offset += 2
        end1 = offset + (2 * len1)
        if end1 > len(payload):
            return {**result, "parse_error": "bindata_link_abs_path_truncated"}
        result["absolute_path"] = payload[offset:end1].decode("utf-16le", errors="replace")
        offset = end1
        if offset + 2 > len(payload):
            return {**result, "parse_error": "bindata_link_rel_len_truncated"}
        len2 = struct.unpack_from("<H", payload, offset)[0]
        offset += 2
        end2 = offset + (2 * len2)
        if end2 > len(payload):
            return {**result, "parse_error": "bindata_link_rel_path_truncated"}
        result["relative_path"] = payload[offset:end2].decode("utf-16le", errors="replace")
        return result

    if offset + 2 > len(payload):
        return {**result, "parse_error": "bindata_storage_id_truncated"}
    storage_id = struct.unpack_from("<H", payload, offset)[0]
    offset += 2
    result["storage_id"] = storage_id
    if data_type == 1:  # EMBEDDING
        if offset + 2 > len(payload):
            return {**result, "parse_error": "bindata_extension_len_truncated"}
        ext_len = struct.unpack_from("<H", payload, offset)[0]
        offset += 2
        ext_end = offset + (2 * ext_len)
        if ext_end > len(payload):
            return {**result, "parse_error": "bindata_extension_truncated"}
        result["extension"] = payload[offset:ext_end].decode(
            "utf-16le", errors="replace"
        ).rstrip("\x00").lower()
    return result


def _detect_image_format(payload: bytes) -> str | None:
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if payload.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if payload.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if payload.startswith(b"BM"):
        return "bmp"
    return None


def _decode_bindata_payload(payload: bytes, compression: int) -> tuple[bytes, str]:
    candidates: list[tuple[bytes, str]] = [(payload, "stored")]
    if compression in {0x0000, 0x0010}:
        try:
            candidates.append((zlib.decompress(payload, -15), "raw-deflate"))
        except zlib.error:
            pass
    for candidate, mode in candidates:
        if _detect_image_format(candidate):
            return candidate, mode
    return payload, "opaque"


def prepare_hwp5_image_for_hwpx(
    asset: dict,
    *,
    max_pixels: int = 20_000_000,
) -> dict:
    """Return PNG/JPEG bytes acceptable to the HWPX engine with an explicit transform receipt."""
    source = bytes(asset.get("data") or b"")
    source_format = str(asset.get("format") or "").lower()
    source_sha256 = hashlib.sha256(source).hexdigest()
    if source_format in {"png", "jpeg"}:
        return {
            "data": source,
            "format": source_format,
            "transform": "passthrough",
            "source_format": source_format,
            "source_sha256": source_sha256,
            "output_sha256": source_sha256,
            "width": None,
            "height": None,
        }
    if source_format != "bmp":
        raise Hwp5ReadError(f"Unsupported image format for HWPX promotion: {source_format or 'unknown'}")

    try:
        with Image.open(io.BytesIO(source)) as image:
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > int(max_pixels):
                raise Hwp5ReadError(
                    f"BMP pixel count exceeds promotion bound: {width}x{height}"
                )
            mode = image.mode
            if mode not in {"RGB", "RGBA"}:
                image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            output = io.BytesIO()
            image.save(output, format="PNG", optimize=False)
            promoted = output.getvalue()
    except Hwp5ReadError:
        raise
    except Exception as exc:
        raise Hwp5ReadError("BMP image could not be safely transcoded to PNG") from exc

    return {
        "data": promoted,
        "format": "png",
        "transform": "bmp-to-png",
        "source_format": "bmp",
        "source_sha256": source_sha256,
        "output_sha256": hashlib.sha256(promoted).hexdigest(),
        "width": width,
        "height": height,
    }


def extract_hwp5_binary_assets(data: bytes) -> dict[int, dict]:
    """Return bounded embedded BinData assets keyed by HWP storage id for promotion use."""
    try:
        ole = olefile.OleFileIO(io.BytesIO(data))
    except Exception as exc:
        raise Hwp5ReadError("Payload is not a valid OLE/CFB HWP container") from exc
    try:
        metadata: dict[int, dict] = {}
        if ole.exists("DocInfo"):
            raw = ole.openstream("DocInfo").read()
            header = _parse_header(ole.openstream("FileHeader").read(256))
            if header.compressed:
                raw = _decompress_stream(raw)
            for tag_id, _level, payload in _iter_records(raw):
                if tag_id != HWPTAG_BIN_DATA:
                    continue
                item = _parse_bindata_record(payload)
                storage_id = item.get("storage_id")
                if storage_id is not None:
                    metadata[int(storage_id)] = item

        result: dict[int, dict] = {}
        for parts in ole.listdir(streams=True, storages=False):
            stream_name = "/".join(parts)
            if not stream_name.startswith("BinData/"):
                continue
            stream_id = _bindata_numeric_id(stream_name)
            if stream_id is None:
                continue
            raw = ole.openstream(stream_name).read()
            meta = metadata.get(int(stream_id), {})
            decoded, storage_mode = _decode_bindata_payload(
                raw, int(meta.get("compression", 0))
            )
            result[int(stream_id)] = {
                "stream": stream_name,
                "storage_id": int(stream_id),
                "extension": meta.get("extension"),
                "compression": meta.get("compression"),
                "storage_mode": storage_mode,
                "raw_sha256": hashlib.sha256(raw).hexdigest(),
                "sha256": hashlib.sha256(decoded).hexdigest(),
                "bytes": len(decoded),
                "format": _detect_image_format(decoded),
                "data": decoded,
            }
        return result
    finally:
        ole.close()


def _parse_rectangle_record(payload: bytes) -> dict:
    result = _opaque_object_record("rectangle", payload, fidelity="structural")
    if len(payload) < 33:
        result["fidelity"] = "inventory"
        result["parse_error"] = "rectangle_record_too_short"
        return result
    result.update({
        "curvature": payload[0],
        "x": list(struct.unpack_from("<iiii", payload, 1)),
        "y": list(struct.unpack_from("<iiii", payload, 17)),
    })
    return result


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

        char_shapes: list[dict] = []
        para_shapes: list[dict] = []
        styles: list[dict] = []
        id_mappings: dict = {}
        face_names: dict[str, list[dict]] = {
            language: [] for language in HWP_FONT_LANGUAGES
        }
        if ole.exists("DocInfo"):
            docinfo_raw = ole.openstream("DocInfo").read()
            if header.compressed:
                docinfo_raw = _decompress_stream(docinfo_raw)
            docinfo_records = list(_iter_records(docinfo_raw))
            for tag_id, _level, record in docinfo_records:
                if tag_id == HWPTAG_ID_MAPPINGS:
                    id_mappings = _parse_id_mappings(record)
                    break

            face_cursor = 0
            face_boundaries: list[tuple[str, int, int]] = []
            for language in HWP_FONT_LANGUAGES:
                amount = int((id_mappings.get("font_counts") or {}).get(language, 0))
                face_boundaries.append((language, face_cursor, face_cursor + amount))
                face_cursor += amount
            seen_faces = 0
            for tag_id, _level, record in docinfo_records:
                if tag_id == HWPTAG_FACE_NAME:
                    parsed_face = _parse_face_name(record)
                    language = next(
                        (
                            name for name, start, end in face_boundaries
                            if start <= seen_faces < end
                        ),
                        "user",
                    )
                    parsed_face["language"] = language
                    parsed_face["font_id"] = len(face_names[language])
                    face_names[language].append(parsed_face)
                    seen_faces += 1
                elif tag_id == HWPTAG_CHAR_SHAPE:
                    char_shapes.append(_parse_docinfo_char_shape(record, len(char_shapes)))
                elif tag_id == HWPTAG_PARA_SHAPE:
                    para_shapes.append(_parse_docinfo_para_shape(record, len(para_shapes)))
                elif tag_id == HWPTAG_STYLE:
                    styles.append(_parse_docinfo_style(record, len(styles)))

            char_shapes = [
                _resolve_char_shape_faces(item, face_names)
                for item in char_shapes
            ]

        streams = ["/".join(parts) for parts in ole.listdir(streams=True, storages=False)]
        binary_items = []
        binary_by_id: dict[int, dict] = {}
        for stream_name in streams:
            if not stream_name.startswith("BinData/"):
                continue
            try:
                binary = ole.openstream(stream_name).read()
            except Exception:
                continue
            item = {
                "stream": stream_name,
                "bin_item_id": _bindata_numeric_id(stream_name),
                "bytes": len(binary),
                "sha256": hashlib.sha256(binary).hexdigest(),
            }
            binary_items.append(item)
            if item["bin_item_id"] is not None:
                binary_by_id[int(item["bin_item_id"])] = item

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
        controls: list[dict] = []
        control_edges: list[dict] = []
        warnings: list[str] = []
        total_chars = 0

        for section_index, section_name in enumerate(section_names):
            raw = ole.openstream(section_name).read()
            if header.compressed:
                raw = _decompress_stream(raw)
            records = list(_iter_records(raw))
            parents = _parent_indexes(records)

            para_header_ord: dict[int, int] = {}
            local_para_ord = 0
            for record_index, (tag_id, _level, _record) in enumerate(records):
                if tag_id == HWPTAG_PARA_HEADER:
                    para_header_ord[record_index] = local_para_ord
                    local_para_ord += 1

            para_header_meta: dict[int, dict] = {}
            para_char_changes: dict[int, list[dict]] = {}
            for record_index, (tag_id, _level, record) in enumerate(records):
                if tag_id == HWPTAG_PARA_HEADER:
                    para_header_meta[record_index] = _parse_para_header(record)
                elif tag_id == HWPTAG_PARA_CHAR_SHAPE:
                    para_header_record = _nearest_ancestor(
                        records, parents, record_index, {HWPTAG_PARA_HEADER}
                    )
                    if para_header_record is not None:
                        para_char_changes[para_header_record] = _parse_para_char_shapes(record)

            ctrl_by_record: dict[int, dict] = {}
            for record_index, (tag_id, level, record) in enumerate(records):
                if tag_id != HWPTAG_CTRL_HEADER:
                    continue
                parsed_ctrl = _parse_ctrl_header(record)
                para_header_record = _nearest_ancestor(
                    records, parents, record_index, {HWPTAG_PARA_HEADER}
                )
                ctrl = {
                    "control_index": len(controls),
                    "section_index": section_index,
                    "section_stream": section_name,
                    "record_index": record_index,
                    "record_level": level,
                    "anchor_paragraph_ordinal": (
                        None
                        if para_header_record is None
                        else para_header_ord.get(para_header_record)
                    ),
                    **parsed_ctrl,
                }
                controls.append(ctrl)
                ctrl_by_record[record_index] = ctrl

            # Header/footer family data lives in the owning LIST_HEADER tail
            # in real HWP files. Enrich the already-created control node with
            # page scope and text-area semantics before paragraph ownership is used.
            for record_index, (tag_id, level, record) in enumerate(records):
                if tag_id != HWPTAG_LIST_HEADER:
                    continue
                ctrl_record = _nearest_ancestor(
                    records, parents, record_index, {HWPTAG_CTRL_HEADER}
                )
                ctrl = None if ctrl_record is None else ctrl_by_record.get(ctrl_record)
                if not ctrl or ctrl.get("ctrl_id") not in {"head", "foot"}:
                    continue
                family = _parse_header_footer_from_list_header(record)
                if family is None:
                    continue
                ctrl.update(family)
                ctrl["family_list_record_index"] = record_index
                ctrl["family_list_record_level"] = level

            table_record_by_control: dict[int, dict] = {}
            for record_index, (tag_id, level, record) in enumerate(records):
                if tag_id != HWPTAG_TABLE:
                    continue
                ctrl_record = _nearest_ancestor(
                    records, parents, record_index, {HWPTAG_CTRL_HEADER}
                )
                ctrl = None if ctrl_record is None else ctrl_by_record.get(ctrl_record)
                if not ctrl or ctrl.get("ctrl_id") != "tbl ":
                    continue
                table_record_by_control[int(ctrl["control_index"])] = {
                    "record_index": record_index,
                    "record_level": level,
                    **_parse_table_record(record),
                }

            cell_by_list_record: dict[int, dict] = {}
            cell_anchor_seen: set[tuple[int, int, int]] = set()
            for record_index, (tag_id, level, record) in enumerate(records):
                if tag_id != HWPTAG_LIST_HEADER:
                    continue
                ctrl_record = _nearest_ancestor(
                    records, parents, record_index, {HWPTAG_CTRL_HEADER}
                )
                ctrl = None if ctrl_record is None else ctrl_by_record.get(ctrl_record)
                if not ctrl or ctrl.get("ctrl_id") != "tbl ":
                    continue
                control_index = int(ctrl["control_index"])
                table_meta = table_record_by_control.get(control_index)
                if table_meta is None:
                    continue
                # The table control may own caption/list headers before the
                # HWPTAG_TABLE record. Physical cell LIST_HEADER records occur
                # after the table geometry record.
                if record_index <= int(table_meta["record_index"]):
                    continue
                cell = _parse_table_cell_from_list_header(record)
                if cell is None:
                    continue
                row = int(cell.get("row", -1))
                col = int(cell.get("column", -1))
                rows = int(table_meta.get("row_count", 0) or 0)
                cols = int(table_meta.get("col_count", 0) or 0)
                if row < 0 or col < 0 or row >= rows or col >= cols:
                    continue
                anchor_key = (control_index, row, col)
                if anchor_key in cell_anchor_seen:
                    warnings.append(
                        f"Duplicate table-cell LIST_HEADER ignored for control={control_index}, row={row}, col={col}."
                    )
                    continue
                cell_anchor_seen.add(anchor_key)
                cell.update({
                    "cell_index": len(cell_by_list_record),
                    "section_index": section_index,
                    "list_record_index": record_index,
                    "list_record_level": level,
                    "control_index": control_index,
                    "paragraph_indexes": [],
                    "paragraph_text": [],
                })
                cell_by_list_record[record_index] = cell

            table_by_control: dict[int, dict] = {}
            for record_index, (tag_id, level, record) in enumerate(records):
                source = {
                    "section_index": section_index,
                    "section_stream": section_name,
                    "record_index": record_index,
                    "record_level": level,
                    "tag_id": tag_id,
                }
                ctrl_record = _nearest_ancestor(
                    records, parents, record_index, {HWPTAG_CTRL_HEADER}
                )
                ctrl = None if ctrl_record is None else ctrl_by_record.get(ctrl_record)

                if tag_id == HWPTAG_PARA_TEXT:
                    scan = _scan_para_text(record)
                    text = scan["text"]
                    remaining = max_text_chars - total_chars
                    if remaining <= 0:
                        warnings.append("Text extraction stopped at max_text_chars.")
                        break
                    if len(text) > remaining:
                        text = text[:remaining]
                        warnings.append("Final paragraph was truncated at max_text_chars.")
                    para_header_record = _nearest_ancestor(
                        records, parents, record_index, {HWPTAG_PARA_HEADER}
                    )
                    list_header_record = _nearest_ancestor(
                        records, parents, record_index, {HWPTAG_LIST_HEADER}
                    )
                    paragraph_index = len(paragraphs)
                    header_meta = (
                        {} if para_header_record is None
                        else dict(para_header_meta.get(para_header_record, {}))
                    )
                    para_shape_id = header_meta.get("para_shape_id")
                    header_meta["resolved_para_shape"] = (
                        para_shapes[int(para_shape_id)]
                        if para_shape_id is not None
                        and 0 <= int(para_shape_id) < len(para_shapes)
                        else None
                    )
                    para_style_id = header_meta.get("para_style_id")
                    header_meta["resolved_style"] = (
                        styles[int(para_style_id)]
                        if para_style_id is not None
                        and 0 <= int(para_style_id) < len(styles)
                        else None
                    )
                    resolved_style = header_meta.get("resolved_style") or {}
                    header_meta["style_para_shape"] = (
                        para_shapes[int(resolved_style["para_shape_id"])]
                        if resolved_style.get("para_shape_id") is not None
                        and 0 <= int(resolved_style["para_shape_id"]) < len(para_shapes)
                        else None
                    )
                    header_meta["style_char_shape"] = (
                        char_shapes[int(resolved_style["char_shape_id"])]
                        if resolved_style.get("char_shape_id") is not None
                        and 0 <= int(resolved_style["char_shape_id"]) < len(char_shapes)
                        else None
                    )
                    run_receipts = _build_run_receipts(
                        text,
                        header_meta,
                        [] if para_header_record is None else para_char_changes.get(para_header_record, []),
                        char_shapes,
                        scan,
                    )
                    flow_kind = _flow_kind_for_control(
                        None if ctrl is None else ctrl.get("ctrl_id")
                    )
                    paragraph = {
                        "paragraph_index": paragraph_index,
                        "paragraph_header_record_index": para_header_record,
                        "source_paragraph_ordinal": (
                            None
                            if para_header_record is None
                            else para_header_ord.get(para_header_record)
                        ),
                        "list_header_record_index": list_header_record,
                        "control_index": None if ctrl is None else ctrl["control_index"],
                        "control_id": None if ctrl is None else ctrl.get("ctrl_id"),
                        "flow_kind": flow_kind,
                        "paragraph_style": header_meta,
                        "runs": run_receipts["runs"],
                        "run_visible_span_fidelity": run_receipts["visible_span_fidelity"],
                        **source,
                        "text": text,
                    }
                    paragraphs.append(paragraph)
                    total_chars += len(text)
                    cell = (
                        None
                        if list_header_record is None
                        else cell_by_list_record.get(list_header_record)
                    )
                    if cell is not None:
                        cell["paragraph_indexes"].append(paragraph_index)
                        cell["paragraph_text"].append(text)
                    if len(paragraphs) >= max_paragraphs:
                        warnings.append("Paragraph extraction stopped at max_paragraphs.")
                        break

                elif tag_id == HWPTAG_TABLE:
                    table = {
                        **source,
                        **_parse_table_record(record),
                        "control_index": None if ctrl is None else ctrl["control_index"],
                        "control_id": None if ctrl is None else ctrl.get("ctrl_id"),
                        "anchor_paragraph_ordinal": (
                            None if ctrl is None else ctrl.get("anchor_paragraph_ordinal")
                        ),
                        "cells": [],
                    }
                    tables.append(table)
                    if ctrl is not None:
                        table_by_control[int(ctrl["control_index"])] = table
                        control_edges.append({
                            "from": f"ctrl:{ctrl['control_index']}",
                            "to": f"table:{len(tables)-1}",
                            "relation": "owns-family-record",
                        })

                elif tag_id == HWPTAG_EQEDIT:
                    equation = {
                        **source,
                        **_parse_equation_record(record),
                        "control_index": None if ctrl is None else ctrl["control_index"],
                        "control_id": None if ctrl is None else ctrl.get("ctrl_id"),
                        "anchor_paragraph_ordinal": (
                            None if ctrl is None else ctrl.get("anchor_paragraph_ordinal")
                        ),
                        "position": None if ctrl is None else {
                            "treat_as_char": ctrl.get("treat_as_char"),
                            "vertical_offset": ctrl.get("vertical_offset"),
                            "horizontal_offset": ctrl.get("horizontal_offset"),
                            "width": ctrl.get("width"),
                            "height": ctrl.get("height"),
                            "z_order": ctrl.get("z_order"),
                            "instance_id": ctrl.get("instance_id"),
                            "vert_rel_to": ctrl.get("vert_rel_to"),
                            "horz_rel_to": ctrl.get("horz_rel_to"),
                        },
                        "position_fidelity": (
                            "structural"
                            if ctrl is not None and ctrl.get("fidelity") == "structural"
                            else "inventory"
                        ),
                    }
                    equations.append(equation)
                    if ctrl is not None:
                        control_edges.append({
                            "from": f"ctrl:{ctrl['control_index']}",
                            "to": f"equation:{len(equations)-1}",
                            "relation": "owns-family-record",
                        })

                elif tag_id == HWPTAG_SHAPE_COMPONENT_PICTURE:
                    picture = {
                        **source,
                        **_parse_picture_record(record),
                        "control_index": None if ctrl is None else ctrl["control_index"],
                        "control_id": None if ctrl is None else ctrl.get("ctrl_id"),
                        "anchor_paragraph_ordinal": (
                            None if ctrl is None else ctrl.get("anchor_paragraph_ordinal")
                        ),
                    }
                    bin_item_id = picture.get("bin_item_id")
                    linked_binary = (
                        None
                        if bin_item_id is None
                        else binary_by_id.get(int(bin_item_id))
                    )
                    picture["binary_link"] = (
                        None if linked_binary is None else dict(linked_binary)
                    )
                    picture["binary_link_fidelity"] = (
                        "structural" if linked_binary is not None else "inventory"
                    )
                    if ctrl is not None and ctrl.get("fidelity") == "structural":
                        picture["control_geometry"] = {
                            "treat_as_char": ctrl.get("treat_as_char"),
                            "vertical_offset": ctrl.get("vertical_offset"),
                            "horizontal_offset": ctrl.get("horizontal_offset"),
                            "width": ctrl.get("width"),
                            "height": ctrl.get("height"),
                            "z_order": ctrl.get("z_order"),
                            "instance_id": ctrl.get("instance_id"),
                        }
                    objects.append(picture)
                    if ctrl is not None:
                        control_edges.append({
                            "from": f"ctrl:{ctrl['control_index']}",
                            "to": f"object:{len(objects)-1}",
                            "relation": "owns-family-record",
                        })
                    if linked_binary is not None:
                        control_edges.append({
                            "from": f"object:{len(objects)-1}",
                            "to": f"bindata:{bin_item_id}",
                            "relation": "references-binary",
                        })

                elif tag_id in {
                    HWPTAG_SHAPE_COMPONENT,
                    HWPTAG_SHAPE_COMPONENT_LINE,
                    HWPTAG_SHAPE_COMPONENT_RECTANGLE,
                    HWPTAG_SHAPE_COMPONENT_ELLIPSE,
                    HWPTAG_SHAPE_COMPONENT_ARC,
                    HWPTAG_SHAPE_COMPONENT_POLYGON,
                }:
                    family = {
                        HWPTAG_SHAPE_COMPONENT: "shape",
                        HWPTAG_SHAPE_COMPONENT_LINE: "line",
                        HWPTAG_SHAPE_COMPONENT_RECTANGLE: "rectangle",
                        HWPTAG_SHAPE_COMPONENT_ELLIPSE: "ellipse",
                        HWPTAG_SHAPE_COMPONENT_ARC: "arc",
                        HWPTAG_SHAPE_COMPONENT_POLYGON: "polygon",
                    }[tag_id]
                    parsed_shape = (
                        _parse_rectangle_record(record)
                        if tag_id == HWPTAG_SHAPE_COMPONENT_RECTANGLE
                        else _opaque_object_record(
                            family,
                            record,
                            fidelity=(
                                "raw-preserved"
                                if tag_id == HWPTAG_SHAPE_COMPONENT
                                else "structural"
                            ),
                        )
                    )
                    shape = {
                        **source,
                        **parsed_shape,
                        "control_index": None if ctrl is None else ctrl["control_index"],
                        "control_id": None if ctrl is None else ctrl.get("ctrl_id"),
                        "anchor_paragraph_ordinal": (
                            None if ctrl is None else ctrl.get("anchor_paragraph_ordinal")
                        ),
                    }
                    objects.append(shape)
                    if ctrl is not None:
                        ctrl["shape_family"] = family
                        ctrl["shape_family_record_index"] = record_index
                        ctrl["shape_family_fidelity"] = parsed_shape.get(
                            "fidelity", "inventory"
                        )
                        control_edges.append({
                            "from": f"ctrl:{ctrl['control_index']}",
                            "to": f"object:{len(objects)-1}",
                            "relation": "owns-shape-family",
                        })

            for list_record_index, cell in cell_by_list_record.items():
                table = table_by_control.get(int(cell["control_index"]))
                if table is None:
                    continue
                table["cells"].append(cell)
                control_edges.append({
                    "from": f"table:{tables.index(table)}",
                    "to": (
                        f"cell:{cell['row']}:{cell['column']}:"
                        f"{cell['control_index']}:{list_record_index}"
                    ),
                    "relation": "contains-cell",
                })
                for paragraph_index in cell["paragraph_indexes"]:
                    control_edges.append({
                        "from": (
                            f"cell:{cell['row']}:{cell['column']}:"
                            f"{cell['control_index']}:{list_record_index}"
                        ),
                        "to": f"paragraph:{paragraph_index}",
                        "relation": "contains-paragraph",
                    })

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
            "id_mappings": id_mappings,
            "face_names": face_names,
            "char_shapes": char_shapes,
            "para_shapes": para_shapes,
            "styles": styles,
            "tables": tables,
            "equations": equations,
            "objects": objects,
            "binary_items": binary_items,
            "controls": controls,
            "control_edges": control_edges,
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
                "run_style": (
                    "semantic"
                    if paragraphs and all(
                        (not item.get("runs")) or all(
                            run.get("fidelity") == "semantic"
                            for run in item.get("runs", [])
                        )
                        for item in paragraphs
                    )
                    else "structural"
                ) if paragraphs else "not-present",
                "nested_text_flows": (
                    "structural"
                    if any(item.get("flow_kind") != "body" for item in paragraphs)
                    else "not-present"
                ),
                "tables": ("semantic" if tables and all(item.get("cells") for item in tables) else "structural") if tables else "not-present",
                "equations": ("semantic" if equations else "not-present"),
                "equation_position": ("structural" if equations and all(item.get("position_fidelity") == "structural" for item in equations) else "inventory") if equations else "not-present",
                "pictures": ("structural" if any(item.get("kind") == "picture" and item.get("binary_link") for item in objects) else "inventory") if any(item["kind"] == "picture" for item in objects) else "not-present",
                "binary_items": "inventory" if binary_items else "not-present",
                "shapes": "raw-preserved" if any(item["kind"] == "shape" for item in objects) else "not-present",
            },
            "authority": "READ_ONLY_LOSS_AWARE",
        }
    finally:
        ole.close()
