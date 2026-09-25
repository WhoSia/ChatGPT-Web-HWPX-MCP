from __future__ import annotations

import argparse
from pathlib import Path

from p341r1_adjudicate import write_adjudication


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Adjudicate a completed P3.41-R1 native Hancom A3 capture pack."
    )
    parser.add_argument("--pack", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--human-out", type=Path)
    args = parser.parse_args()
    result = write_adjudication(args.pack, args.out, args.human_out)
    print(
        f"{result['native_world_contact']['status']} "
        f"fixtures={result['native_world_contact']['fixture_count']} "
        f"pages={result['native_world_contact']['page_count_total']} "
        f"review_signals={result['review_signal_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
