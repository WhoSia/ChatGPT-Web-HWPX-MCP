from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from p316_stability_builder import build_version_indexed_packet


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--repeat",
        action="append",
        nargs=2,
        metavar=("PACK_DIR", "FONT_CUSTODY_JSON"),
        required=True,
        help="repeat this argument at least three times",
    )
    p.add_argument("--out", required=True)
    args = p.parse_args()

    pairs = [(Path(pack), Path(font)) for pack, font in args.repeat]
    packet = build_version_indexed_packet(pairs)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(packet, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(packet["adjudication"], ensure_ascii=False, indent=2))
    return 0 if packet["adjudication"]["verdict"] != "SINGLE_VERSION_STABILITY_HOLD" else 2


if __name__ == "__main__":
    raise SystemExit(main())
