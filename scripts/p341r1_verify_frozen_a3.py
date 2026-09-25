from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from p340r1_capture_pack import sha256_file
from p341r1_capture_pack import (
    FIXTURES,
    FROZEN_BENCHMARK_COMMIT,
    FROZEN_MATERIALIZATION_METHOD,
    materialize,
)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="p341r1-verify-") as tmp:
        pack = Path(tmp) / "pack"
        manifest = materialize(ROOT, pack)
        rows = []
        for fixture in manifest["fixtures"]:
            path = pack / fixture["path"]
            actual = sha256_file(path)
            expected = str(fixture["sha256"])
            if actual != expected:
                raise RuntimeError(
                    f"frozen A3 verification drift for {fixture['fixture_id']}: "
                    f"expected {expected}, got {actual}"
                )
            rows.append({
                "fixture_id": fixture["fixture_id"],
                "archetype": fixture["archetype"],
                "sha256": actual,
            })

    print(json.dumps({
        "status": "PASS",
        "frozen_benchmark_commit": FROZEN_BENCHMARK_COMMIT,
        "materialization_method": FROZEN_MATERIALIZATION_METHOD,
        "fixture_count": len(FIXTURES),
        "fixtures": rows,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
