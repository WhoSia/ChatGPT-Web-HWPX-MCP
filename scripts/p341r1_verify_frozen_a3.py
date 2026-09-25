from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from p340r1_capture_pack import sha256_file
from p341r1_capture_pack import FIXTURES, FROZEN_BENCHMARK_COMMIT


def main() -> int:
    rows = []
    for fixture in FIXTURES:
        path = ROOT / "artifacts" / str(fixture["filename"])
        if not path.is_file():
            raise RuntimeError(f"missing frozen A3 output: {path}")
        actual = sha256_file(path)
        expected = str(fixture["sha256"])
        if actual != expected:
            raise RuntimeError(
                f"A3 drift for {fixture['fixture_id']}: expected {expected}, got {actual}"
            )
        rows.append({
            "fixture_id": fixture["fixture_id"],
            "archetype": fixture["archetype"],
            "sha256": actual,
        })
    print(json.dumps({
        "status": "PASS",
        "frozen_benchmark_commit": FROZEN_BENCHMARK_COMMIT,
        "fixtures": rows,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
