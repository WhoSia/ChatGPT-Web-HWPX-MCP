from __future__ import annotations

import argparse
import json
from pathlib import Path

from p315_replay_builder import build_cross_version_packet


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--first-pack", required=True)
    p.add_argument("--first-font-custody", required=True)
    p.add_argument("--second-pack", required=True)
    p.add_argument("--second-font-custody", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    packet = build_cross_version_packet(
        Path(args.first_pack),
        Path(args.first_font_custody),
        Path(args.second_pack),
        Path(args.second_font_custody),
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(packet["adjudication"], ensure_ascii=False, indent=2))
    return 0 if packet["adjudication"]["promotion_reopened"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
