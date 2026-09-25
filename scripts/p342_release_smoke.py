from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

from p342_mutation_footprint import (
    build_mutation_footprint,
    enforce_preservation_grade,
    mutation_footprint_contract,
)


def write_fixture(path: Path, payload: bytes) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", b"application/hwp+zip")
        archive.writestr("Contents/header.xml", b"<header/>")
        archive.writestr("Contents/section0.xml", payload)


with tempfile.TemporaryDirectory(prefix="p342-") as tmp:
    root = Path(tmp)
    before = root / "before.hwpx"
    after = root / "after.hwpx"
    write_fixture(before, b"<section><p>a</p></section>")
    write_fixture(after, b"<section><p>b</p></section>")
    cert = build_mutation_footprint(
        before,
        after,
        {
            "changed_parts": ["Contents/section0.xml"],
            "required_changed_parts": ["Contents/section0.xml"],
        },
    )
    assert mutation_footprint_contract()["phase"] == "P3.42"
    assert cert["preservation"]["actual_grade"] == "TARGETED_PARTS_ONLY"
    assert enforce_preservation_grade(cert, "TARGETED_PARTS_ONLY")["passed"]

print("P3.42 release smoke PASS")
