from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from p325_regression_corpus import materialize_p325_regression_corpus


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("artifacts/p325-regression-corpus"))
    args = parser.parse_args()
    manifest = materialize_p325_regression_corpus(args.out)
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
