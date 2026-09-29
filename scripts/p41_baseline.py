from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

import server
from p41_operational import PRODUCT, profile_operations, runtime_compatibility_matrix

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="p41-baseline.json")
    parser.add_argument("--samples", type=int, default=3)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        existing = root / "existing.hwpx"
        server.materialize_hwpx(existing, "P4.1 baseline\n둘째 문단", "P4.1")
        def create_validate():
            target = root / "candidate.hwpx"
            server.materialize_hwpx(target, "P4.1 baseline\n둘째 문단", "P4.1")
            server.validate_hwpx_package(target, ingress=True)
        def validate_existing():
            server.validate_hwpx_package(existing, ingress=True)
        def import_product():
            proc = subprocess.run(
                [sys.executable, "-c", "import server_p2; assert server_p2.P2_VERSION=='0.27.0-p4.1'"],
                capture_output=True, text=True, timeout=20, check=False,
            )
            if proc.returncode:
                raise RuntimeError(proc.stderr or proc.stdout or "server_p2 import failed")
        result = profile_operations(
            {
                "server_p2_import": (import_product, 15000.0),
                "minimal_hwpx_create_validate": (create_validate, 5000.0),
                "existing_hwpx_validate": (validate_existing, 3000.0),
            },
            sample_count=args.samples,
        )
    result["runtime_compatibility"] = runtime_compatibility_matrix()
    result["product"] = PRODUCT
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())
