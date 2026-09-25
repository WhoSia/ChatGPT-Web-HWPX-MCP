from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from p340r1_capture_pack import capture_pdf


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", required=True)
    parser.add_argument("--fixture-id", required=True)
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--hancom-version", required=True)
    parser.add_argument("--hancom-sha256", required=True)
    parser.add_argument("--dpi", required=True, type=int)
    parser.add_argument("--runner-sha256", required=True)
    args = parser.parse_args()
    receipt = capture_pdf(
        pack=Path(args.pack), fixture_id=args.fixture_id, pdf=Path(args.pdf),
        hancom_version=args.hancom_version, hancom_sha256=args.hancom_sha256,
        dpi=args.dpi, runner_sha256=args.runner_sha256,
    )
    print(json.dumps({"fixture_id": args.fixture_id, "pages": len(receipt["capture"]["pages"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
