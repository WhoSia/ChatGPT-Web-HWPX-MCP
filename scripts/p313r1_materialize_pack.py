from __future__ import annotations

import argparse
import json
from pathlib import Path

from p313r1_fixture_pack import materialize_pre_hancom_pack


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default="artifacts/p313r1-hancom-capture-pack",
        help="output directory for the self-materialized capture pack",
    )
    args = parser.parse_args()
    result = materialize_pre_hancom_pack(Path(args.out))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
