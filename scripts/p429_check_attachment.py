"""Compare a downloaded HWPX attachment with a committed delivery receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


def assess_attachment(path: Path, receipt: dict) -> dict:
    revision = receipt.get("revision")
    expected = receipt.get("sha256")
    if type(revision) is not int or revision < 1:
        raise ValueError("expected a positive committed revision")
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("expected a lowercase SHA-256 digest")
    if path.suffix.lower() != ".hwpx":
        raise ValueError("expected an HWPX attachment")
    with path.open("rb") as stream:
        observed = hashlib.file_digest(stream, "sha256").hexdigest()
    return {
        "revision": revision,
        "expected_sha256": expected,
        "observed_sha256": observed,
        "verdict": "ATTACHMENT_MATCH" if observed == expected else "ATTACHMENT_MISMATCH",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("attachment", type=Path)
    parser.add_argument("delivery_receipt", type=Path)
    args = parser.parse_args()
    try:
        receipt = json.loads(args.delivery_receipt.read_text(encoding="utf-8-sig"))
        if not isinstance(receipt, dict):
            raise ValueError("expected a JSON object")
        result = assess_attachment(args.attachment, receipt)
    except (OSError, ValueError) as exc:
        result = {"verdict": "CHECK_FAILED", "error_type": type(exc).__name__}
    print(json.dumps(result))
    return 0 if result["verdict"] == "ATTACHMENT_MATCH" else 1


if __name__ == "__main__":
    raise SystemExit(main())
