from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from p315_cross_version import adjudicate_cross_version_replay


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--first", required=True)
    p.add_argument("--second", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    packet = {
        "schema": "chatgpt-web-hwpx-mcp/cross-version-replay/p3.15/v1",
        "versions": [load(args.first), load(args.second)],
    }
    result = adjudicate_cross_version_replay(packet)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["promotion_reopened"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
