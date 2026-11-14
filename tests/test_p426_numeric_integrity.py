"""Regression: no nonfinite numeric values in composed scientific report cells."""
import math
import unittest

from hwpx_mcp.interfaces.p425_report_presets import _as_native_table


class NativeReportNumericIntegrityTests(unittest.TestCase):
    def test_rejects_nonfinite_floating_point_cells(self):
        for value in (float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=repr(value)):
                with self.assertRaisesRegex(ValueError, "REPORT_TABLE_NONFINITE_VALUE"):
                    _as_native_table({"cells": [["measurement"], [value]]})

    def test_accepts_finite_scientific_measurements_and_preserves_sign(self):
        table = _as_native_table({
            "cells": [["V", "I"], [0.0, -1.25e-9], [12.5, 0.625]]
        })
        self.assertEqual(table["rows"], 3)
        self.assertEqual(table["cols"], 2)
        self.assertEqual(table["cells"][1], ["0.0", "-1.25e-09"])

    def test_rejects_boolean_as_numeric_value(self):
        with self.assertRaisesRegex(ValueError, "REPORT_TABLE_VALUE_INVALID"):
            _as_native_table({"cells": [["flag"], [True]]})


if __name__ == "__main__":
    unittest.main()
