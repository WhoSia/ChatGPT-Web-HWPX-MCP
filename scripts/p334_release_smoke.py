#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from p334_rare_feature_registry import (
    EVIDENCE_KEYS,
    evaluate_rare_feature,
    rare_feature_registry,
    ux_regression_contract,
)


def main() -> int:
    registry = rare_feature_registry()
    assert registry["phase"] == "P3.34"
    assert registry["features"]["smart_connectline"]["state"] == "BLOCKED_SEMANTIC_AMBIGUITY"
    assert registry["features"]["column_insertion"]["state"] == "BOUNDED_PRODUCTION_AUTHORITY"
    assert registry["features"]["column_insertion"]["authority"] == "COUNT1_LEFT_RIGHT_NATIVE_COLUMN_INSERTION"

    evidence = {key: True for key in EVIDENCE_KEYS}
    assert evaluate_rare_feature("polygon_preserving_resize", evidence)["promotion_ready"] is True
    assert evaluate_rare_feature("smart_connectline", evidence)["promotion_ready"] is False

    ux = ux_regression_contract()
    assert ux["policy"] == "PERIODIC_PRODUCT_UX_SMOKE"
    assert "every production phase before closure" in ux["cadence"]
    print("P3.34 rare-feature registry + periodic UX guard PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
