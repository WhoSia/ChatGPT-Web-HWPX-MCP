from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from p340r1_capture_pack import deterministic_zip, validate_complete, write_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", required=True)
    parser.add_argument("--zip", required=True)
    args = parser.parse_args()
    pack, destination = Path(args.pack), Path(args.zip)
    validation = validate_complete(pack)
    write_json(pack / "capture-validation.json", validation)
    if not validation["complete"]:
        print(json.dumps(validation, indent=2))
        return 2
    digest = deterministic_zip(pack, destination)
    print(json.dumps({"zip": str(destination), "sha256": digest, **validation}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
