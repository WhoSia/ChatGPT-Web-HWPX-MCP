from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from p328_regression_corpus import materialize_p328_regression_corpus


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("artifacts/p328-regression-corpus"))
    args = parser.parse_args()
    print(json.dumps(materialize_p328_regression_corpus(args.out), ensure_ascii=False))


if __name__ == "__main__":
    main()
