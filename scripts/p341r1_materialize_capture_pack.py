from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from p341r1_capture_pack import materialize


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = materialize(ROOT, Path(args.out))
    print(json.dumps({
        "runner_commit": result["source"]["runner_commit"],
        "frozen_benchmark_commit": result["benchmark_authority"]["frozen_commit"],
        "fixtures": len(result["fixtures"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
