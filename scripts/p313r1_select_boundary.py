from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from p313r1_fixture_pack import select_boundary_candidate


def collect(root: Path, family: str) -> list[dict]:
    items = []
    for candidate_dir in sorted((root / "calibration").glob(f"{family}-*")):
        receipt_path = candidate_dir / "capture" / "render-receipt.json"
        if not receipt_path.is_file():
            continue
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        metrics = receipt.get("metrics") or {}
        suffix = candidate_dir.name.split("-", 1)[1]
        magnitude = int(suffix) - 10000 if family == "advance" else int(suffix)
        items.append({
            "candidate_id": candidate_dir.name,
            "magnitude": magnitude,
            "line_break_diverged": metrics.get("line_break_equal") is False,
            "render_receipt": str(receipt_path.relative_to(root)).replace("\\", "/"),
            "metrics": metrics,
        })
    return items


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--pack", required=True)
    args = p.parse_args()
    root = Path(args.pack)

    advance = select_boundary_candidate(collect(root, "advance"))
    frame = select_boundary_candidate(collect(root, "frame"))
    result = {
        "schema": "chatgpt-web-hwpx-mcp/boundary-selection/p3.13-r1/v1",
        "advance": advance,
        "frame": frame,
        "ready_for_p314": bool(advance.get("selected") and frame.get("selected")),
        "authority": (
            "HANCOM_OBSERVED_NEAR_WRAP_BOUNDARY_READY"
            if advance.get("selected") and frame.get("selected")
            else "BOUNDARY_SELECTION_HOLD"
        ),
    }
    output = root / "boundary-selection.json"
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ready_for_p314"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
