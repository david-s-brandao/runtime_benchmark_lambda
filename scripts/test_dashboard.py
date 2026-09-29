"""Validation and rendering smoke tests for the checked-in daily report."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.dashboard import ROOT, render, validate_report


class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads((ROOT / "reports/20260929T082758Z_daily_report.json").read_text())

    def test_report_and_six_pngs(self):
        validate_report(self.report)
        with tempfile.TemporaryDirectory() as directory:
            render(self.report, Path(directory))
            pngs = list(Path(directory).glob("benchmark_*.png"))
            self.assertEqual(len(pngs), 6)
            for path in pngs:
                self.assertEqual(path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_inconsistent_counts_rejected(self):
        report = copy.deepcopy(self.report)
        report["functions"]["rust_function"]["cloudwatch_by_version"]["$LATEST"]["attempts"] = 1
        with self.assertRaisesRegex(ValueError, "inconsistent invocation"):
            validate_report(report)

    def test_bad_percentile_rejected(self):
        report = copy.deepcopy(self.report)
        report["functions"]["java_function"]["cloudwatch_by_version"]["$LATEST"][
            "duration_ms_success_only"]["p99"] = -1
        with self.assertRaisesRegex(ValueError, "p99"):
            validate_report(report)

    def test_unavailable_xray_is_not_zero_error_rate(self):
        report = copy.deepcopy(self.report)
        report["functions"]["rust_function"]["xray"]["error_count"] = 0
        with self.assertRaisesRegex(ValueError, "zero traces"):
            validate_report(report)

    def test_missing_stages_allowed_but_broken_stages_rejected(self):
        report = copy.deepcopy(self.report)
        report["functions"]["rust_function"]["cloudwatch_by_version"]["$LATEST"][
            "stages_cold_success_only"] = None
        validate_report(report)
        report["functions"]["java_function"]["cloudwatch_by_version"]["$LATEST"][
            "stages_cold_success_only"]["get_ms"]["p95"] = 999999
        with self.assertRaisesRegex(ValueError, "get_ms"):
            validate_report(report)


if __name__ == "__main__":
    unittest.main()
