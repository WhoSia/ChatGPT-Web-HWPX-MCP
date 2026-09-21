from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from p317_regression_corpus import materialize_p317_regression_corpus


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="artifacts/p317-regression-corpus")
    args = p.parse_args()
    result = materialize_p317_regression_corpus(Path(args.out))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
