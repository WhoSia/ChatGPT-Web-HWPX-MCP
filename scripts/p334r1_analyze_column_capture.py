#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def archive(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as zf:
        bad = zf.testzip()
        if bad:
            raise RuntimeError(f"CRC failure in {path}: {bad}")
        return {name: zf.read(name) for name in zf.namelist()}


def xml_ok(parts: dict[str, bytes]) -> bool:
    for name, data in parts.items():
        if name.endswith((".xml", ".rdf", ".opf")):
            ET.fromstring(data)
    return True


def first_table(parts: dict[str, bytes]) -> tuple[str, bytes]:
    for name in sorted(parts):
        if not (name.endswith(".xml") and ("Contents/" in name or "content" in name.lower())):
            continue
        data = parts[name]
        m = re.search(rb"<(?:[A-Za-z_][\w.-]*:)?tbl\b.*?</(?:[A-Za-z_][\w.-]*:)?tbl>", data, re.DOTALL)
        if m:
            return name, m.group(0)
    raise RuntimeError("No table found")


def iattr(chunk: bytes, tag: str, attr: str, default: int | None = None) -> int | None:
    m = re.search(
        rb"<(?:[A-Za-z_][\w.-]*:)?" + tag.encode() + rb"\b[^>]*\b" + attr.encode() + rb'="(-?\d+)"',
        chunk,
    )
    return int(m.group(1)) if m else default


def table_report(table: bytes) -> dict:
    colcnt = iattr(table, "tbl", "colCnt")
    rowcnt = iattr(table, "tbl", "rowCnt")
    width = iattr(table, "sz", "width")
    cells = []
    for m in re.finditer(rb"<(?:[A-Za-z_][\w.-]*:)?tc\b.*?</(?:[A-Za-z_][\w.-]*:)?tc>", table, re.DOTALL):
        tc = m.group(0)
        cells.append({
            "row": iattr(tc, "cellAddr", "rowAddr"),
            "col": iattr(tc, "cellAddr", "colAddr"),
            "rowSpan": iattr(tc, "cellSpan", "rowSpan", 1),
            "colSpan": iattr(tc, "cellSpan", "colSpan", 1),
            "width": iattr(tc, "cellSz", "width"),
            "height": iattr(tc, "cellSz", "height"),
        })
    cells.sort(key=lambda x: (x["row"] if x["row"] is not None else -1, x["col"] if x["col"] is not None else -1))
    return {"rowCnt": rowcnt, "colCnt": colcnt, "tableWidth": width, "cells": cells}


def compare(source: Path, target: Path) -> dict:
    sp = archive(source)
    tp = archive(target)
    xml_ok(sp)
    xml_ok(tp)
    sname, stable = first_table(sp)
    tname, ttable = first_table(tp)
    names = sorted(set(sp) | set(tp))
    changed = [n for n in names if sp.get(n) != tp.get(n)]
    return {
        "source": str(source),
        "target": str(target),
        "source_sha256": sha(source),
        "target_sha256": sha(target),
        "source_bytes": source.stat().st_size,
        "target_bytes": target.stat().st_size,
        "source_table_part": sname,
        "target_table_part": tname,
        "source_table": table_report(stable),
        "target_table": table_report(ttable),
        "changed_entries": changed,
        "zip_entry_count_source": len(sp),
        "zip_entry_count_target": len(tp),
        "crc_pass": True,
        "xml_parse_pass": True,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", default="artifacts/p334r1-column-insertion-pack")
    args = ap.parse_args()
    root = Path(args.pack)
    manifest = json.loads((root / "capture-manifest.json").read_text(encoding="utf-8"))
    reports = []
    missing = []
    for case in manifest["cases"]:
        d = root / case["id"]
        source = d / "source.hwpx"
        target = d / "target.hwpx"
        if not target.exists():
            missing.append(case["id"])
            continue
        report = {"case_id": case["id"], "manual": case["manual"], **compare(source, target)}
        (d / "analysis.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        reports.append(report)

    summary = {
        "schema": "chatgpt-web-hwpx-mcp/p3.34-r1/column-insertion-analysis/v1",
        "cases_analyzed": len(reports),
        "cases_missing": missing,
        "reports": reports,
    }
    (root / "analysis-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"analyzed": len(reports), "missing": missing}, ensure_ascii=False))
    return 0 if not missing else 2


if __name__ == "__main__":
    raise SystemExit(main())
