from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from hwp5_reader import extract_hwp5_binary_assets, parse_hwp5_bytes
from common_ir import hwp5_to_common_ir, extract_common_ir, search_common_ir

SOURCE = Path(os.environ.get("P36_REAL_HWP", "/tmp/hancom-hwp5-spec.hwp"))


def main() -> None:
    data = SOURCE.read_bytes()
    parsed = parse_hwp5_bytes(data, max_text_chars=500_000)
    if not parsed.get("ok") or not parsed.get("readable"):
        raise RuntimeError(f"official HWP sample was not readable: {parsed.get('block_reason')}")
    if parsed.get("format") != "hwp5":
        raise RuntimeError(f"unexpected format: {parsed.get('format')}")
    if not parsed.get("paragraphs"):
        raise RuntimeError("official HWP sample yielded no paragraphs")

    digest = hashlib.sha256(data).hexdigest()
    ir = hwp5_to_common_ir(
        parsed,
        source_sha256=digest,
        filename=SOURCE.name,
    )
    semantic = extract_common_ir(
        ir,
        minimum_fidelity="semantic",
        max_blocks=1000,
    )
    assets = extract_hwp5_binary_assets(data)

    report = {
        "source_bytes": len(data),
        "source_sha256": digest,
        "version": parsed.get("version"),
        "paragraphs": len(parsed.get("paragraphs", [])),
        "tables": len(parsed.get("tables", [])),
        "equations": len(parsed.get("equations", [])),
        "objects": len(parsed.get("objects", [])),
        "binary_items": len(parsed.get("binary_items", [])),
        "controls": len(parsed.get("controls", [])),
        "control_edges": len(parsed.get("control_edges", [])),
        "fidelity": parsed.get("fidelity", {}),
        "ir_blocks": ir.get("block_count"),
        "semantic_or_better_blocks": semantic.get("eligible_block_count"),
        "recovered_binary_assets": len(assets),
        "warnings": parsed.get("warnings", []),
    }
    print("P3.6 REAL_HWP_PARSE_PASS")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
