from __future__ import annotations

import io
import struct
import zlib
from dataclasses import dataclass

import olefile

HWP5_SIGNATURE = b"HWP Document File" + (b"\x00" * 15)
HWPTAG_PARA_TEXT = 0x43


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
                "text": "",
                "warnings": [
                    "Encrypted/DRM HWP content is not decoded by the read-only lane."
                ],
            }

        streams = ["/".join(parts) for parts in ole.listdir(streams=True, storages=False)]
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
        warnings: list[str] = []
        total_chars = 0
        for section_index, section_name in enumerate(section_names):
            raw = ole.openstream(section_name).read()
            if header.compressed:
                raw = _decompress_stream(raw)
            record_index = 0
            for tag_id, level, record in _iter_records(raw):
                if tag_id != HWPTAG_PARA_TEXT:
                    record_index += 1
                    continue
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
                            "section_index": section_index,
                            "section_stream": section_name,
                            "record_index": record_index,
                            "record_level": level,
                            "text": text,
                        }
                    )
                    total_chars += len(text)
                    if len(paragraphs) >= max_paragraphs:
                        warnings.append("Paragraph extraction stopped at max_paragraphs.")
                        break
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
            "text": "\n".join(item["text"] for item in paragraphs),
            "preview_text": preview_text[:20000],
            "preview_text_truncated": len(preview_text) > 20000,
            "streams": streams[:512],
            "streams_truncated": len(streams) > 512,
            "warnings": warnings + [
                "HWP 5.x read lane is text-first and does not yet claim layout/table/object fidelity.",
                "C0 control atoms are stripped rather than interpreted as visible text.",
            ],
            "authority": "READ_ONLY_LOSS_AWARE",
        }
    finally:
        ole.close()
