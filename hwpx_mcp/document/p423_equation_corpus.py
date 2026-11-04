"""Extract minimal EqEdit-only evidence from HWPX without leaking document prose.

Never publish original HWPX, body text, student identifiers or user annotations
as a side effect of gathering golden equations. This module is read-only.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import xml.etree.ElementTree as ET
import zipfile

MAX_SECTION_BYTES = 8 * 1024 * 1024
MAX_EQUATIONS = 2000
MAX_SECTIONS = 128
MAX_MEMBERS = 5000
MAX_SCRIPT_CHARS = 65536


@dataclass(frozen=True)
class EquationEvidence:
    section: str
    index: int
    script: str
    sha256: str


def extract_equations(path: str | Path) -> tuple[EquationEvidence, ...]:
    """Read native hp:script elements in section and document order.

    No paragraph text, names, page images or metadata are returned. Parsing
    errors and resource bounds fail closed rather than returning partial data.
    """
    output: list[EquationEvidence] = []
    with zipfile.ZipFile(path, "r") as archive:
        names = archive.namelist()
        if len(names) > MAX_MEMBERS:
            raise ValueError("HWPX has too many ZIP members")
        if len(names) != len(set(names)):
            raise ValueError("HWPX contains duplicate ZIP members")
        sections = sorted(
            (name for name in names
             if name.startswith("Contents/section") and name.endswith(".xml")),
            key=lambda name: (len(name), name),
        )
        if len(sections) > MAX_SECTIONS:
            raise ValueError("HWPX has too many sections")
        if not sections:
            raise ValueError("HWPX has no Contents/section*.xml")
        for section in sections:
            info = archive.getinfo(section)
            if info.file_size > MAX_SECTION_BYTES:
                raise ValueError("HWPX section exceeds safe XML limit")
            raw = archive.read(section)
            if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
                raise ValueError("DOCTYPE/ENTITY not permitted in section XML")
            root = ET.fromstring(raw)
            index = 0
            for element in root.iter():
                if element.tag.split("}")[-1] != "equation":
                    continue
                scripts = [
                    node.text or ""
                    for node in element.iter()
                    if node.tag.split("}")[-1] == "script"
                ]
                if len(scripts) != 1:
                    raise ValueError("equation must have exactly one script")
                script = scripts[0]
                if len(script) > MAX_SCRIPT_CHARS:
                    raise ValueError("equation script exceeds safe limit")
                if len(output) >= MAX_EQUATIONS:
                    raise ValueError("too many equations")
                output.append(EquationEvidence(
                    section, index, script,
                    hashlib.sha256(script.encode("utf-8")).hexdigest(),
                ))
                index += 1
    return tuple(output)


def pair_equations(
    before: tuple[EquationEvidence, ...],
    after: tuple[EquationEvidence, ...],
) -> tuple[dict[str, object], ...]:
    """Pair strictly by section and index; refuse reorders/inserts.

    Index matching is valid only after a reviewer confirms the underlying
    equation order is preserved. A changed script is NOT automatically a
    correction or proof of render fidelity.
    """
    keys_before = [(x.section, x.index) for x in before]
    keys_after = [(x.section, x.index) for x in after]
    if keys_before != keys_after:
        raise ValueError("equation topology mismatch; manual alignment needed")
    return tuple({
        "section": left.section,
        "index": left.index,
        "before_sha256": left.sha256,
        "after_sha256": right.sha256,
        "changed": left.script != right.script,
    } for left, right in zip(before, after))
