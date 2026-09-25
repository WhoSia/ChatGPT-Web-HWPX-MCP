from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from p335_registry import intake_source
from p342_corpus_evidence import build_corpus_coverage_ledger

DEFAULT_METADATA = ROOT / "corpus" / "p342-public-corpus-metadata.json"


def materialize(metadata_path: Path) -> dict:
    rows = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        raise ValueError("public corpus metadata must be a non-empty list")
    records = [intake_source(dict(row)) for row in rows]
    ledger = build_corpus_coverage_ledger(records)
    if ledger["denominators"]["registered_sources"] != len(rows):
        raise RuntimeError("public corpus denominator drift")
    if ledger["denominators"]["metadata_only_sources"] != len(rows):
        raise RuntimeError(
            "metadata-only census unexpectedly acquired or inferred binary evidence"
        )
    return {
        **ledger,
        "seed_policy": {
            "metadata_only": True,
            "network_fetch_performed": False,
            "binary_acquisition": "WITHHELD",
            "purpose": (
                "Freeze a prospective official-public-HWPX denominator without "
                "promoting page listings to parser/render/design evidence."
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = materialize(args.metadata)
    payload = json.dumps(
        result, ensure_ascii=False, sort_keys=True, indent=2
    ) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
    summary = {
        "status": "PASS",
        "sources": result["denominators"]["registered_sources"],
        "metadata_only": result["denominators"]["metadata_only_sources"],
        "ledger_sha256": result["ledger_sha256"],
        "reuse_rights": next(
            item["counts"]
            for item in result["probe_summary"]
            if item["probe_id"] == "REUSE_RIGHTS_EXPLICIT"
        ),
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
