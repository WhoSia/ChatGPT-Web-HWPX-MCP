from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


REQUIRED = {
    "mimetype",
    "Contents/header.xml",
    "Contents/section0.xml",
    "META-INF/container.xml",
}


def validate_hwpx_package_light(path: Path) -> dict:
    """Standalone HWPX structural validation without server/OAuth initialization."""
    with zipfile.ZipFile(path, "r") as zf:
        infos = zf.infolist()
        if not infos:
            raise ValueError("Empty HWPX package")
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate ZIP entry names are not allowed")
        if infos[0].filename != "mimetype":
            raise ValueError("HWPX mimetype must be first ZIP entry")
        if infos[0].compress_type != zipfile.ZIP_STORED:
            raise ValueError("HWPX mimetype must be stored without compression")
        if zf.read("mimetype") != b"application/hwp+zip":
            raise ValueError("Invalid HWPX mimetype signature")
        missing = sorted(REQUIRED - set(names))
        if missing:
            raise ValueError(f"Missing required HWPX entries: {', '.join(missing)}")
        bad = zf.testzip()
        if bad is not None:
            raise ValueError(f"CRC failure in ZIP entry: {bad}")

        parsed = 0
        for info in infos:
            lower = info.filename.lower()
            if not lower.endswith((".xml", ".hpf", ".rdf", ".opf")):
                continue
            payload = zf.read(info.filename)
            upper = payload.upper()
            if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
                raise ValueError(f"DTD/entity declarations are not allowed: {info.filename}")
            ET.fromstring(payload)
            parsed += 1

    return {
        "valid": True,
        "zip_entries": len(infos),
        "parsed_xml_entries": parsed,
        "required_entries": sorted(REQUIRED),
    }
