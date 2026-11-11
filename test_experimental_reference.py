import unittest

from scripts.experimental_reference import (
    build_reference_rates,
    estimate_reference,
    normalize_cep_prefix,
)
from scripts.audit_data_sources import DATA_DIR, OFFICIAL_FILE


class ExperimentalReferenceTests(unittest.TestCase):
    def test_normalizes_full_cep_and_prefix(self):
        self.assertEqual(normalize_cep_prefix("01005"), "01005")
        self.assertEqual(normalize_cep_prefix("01005-020"), "01005")
        self.assertEqual(normalize_cep_prefix("1005020"), "01005")

    def test_rejects_invalid_cep(self):
        with self.assertRaises(ValueError):
            normalize_cep_prefix("1234")

    def test_estimate_requires_confirmed_iptu_area(self):
        reference = {
            "target": "ITBI declared purchase value",
            "area_basis": "IPTU built area",
            "reference_period": {"start": "2026-01-01", "end": "2026-09-07"},
            "temporal_backtest": {},
            "profiles": {
                "by_cep_prefix5_and_iptu_pattern": {},
                "by_cep_prefix5": {},
                "by_iptu_pattern_citywide": {
                    "22": {
                        "count": 100,
                        "p10_brl_per_m2": 3000.0,
                        "median_brl_per_m2": 5000.0,
                        "p90_brl_per_m2": 8000.0,
                    }
                },
                "citywide": {
                    "count": 100,
                    "p10_brl_per_m2": 2000.0,
                    "median_brl_per_m2": 4000.0,
                    "p90_brl_per_m2": 9000.0,
                },
            },
        }

        with self.assertRaisesRegex(ValueError, "Confirme"):
            estimate_reference(reference, 80, "01005", "22", False)

    def test_estimate_returns_median_and_observed_comparable_range(self):
        reference = {
            "target": "ITBI declared purchase value",
            "area_basis": "IPTU built area",
            "reference_period": {"start": "2026-01-01", "end": "2026-09-07"},
            "temporal_backtest": {},
            "profiles": {
                "by_cep_prefix5_and_iptu_pattern": {},
                "by_cep_prefix5": {},
                "by_iptu_pattern_citywide": {
                    "22": {
                        "count": 100,
                        "p10_brl_per_m2": 3000.0,
                        "median_brl_per_m2": 5000.0,
                        "p90_brl_per_m2": 8000.0,
                    }
                },
                "citywide": {
                    "count": 100,
                    "p10_brl_per_m2": 2000.0,
                    "median_brl_per_m2": 4000.0,
                    "p90_brl_per_m2": 9000.0,
                },
            },
        }

        estimate = estimate_reference(reference, 80, "01005", "22", True)

        self.assertEqual(estimate["estimated_value_brl"], 400000)
        self.assertEqual(
            estimate["observed_comparable_range_brl"]["p10"], 240000
        )
        self.assertEqual(
            estimate["observed_comparable_range_brl"]["p90"], 640000
        )
        self.assertEqual(
            estimate["comparable_support"]["scope"], "iptu_pattern_citywide"
        )

    def test_estimate_without_pattern_uses_cep_profile_only_with_enough_support(self):
        reference = {
            "target": "ITBI declared purchase value",
            "area_basis": "IPTU built area",
            "reference_period": {"start": "2026-01-01", "end": "2026-09-07"},
            "temporal_backtest": {},
            "profiles": {
                "by_cep_prefix5_and_iptu_pattern": {},
                "by_cep_prefix5": {
                    "01005": {
                        "count": 35,
                        "p10_brl_per_m2": 3500.0,
                        "median_brl_per_m2": 5000.0,
                        "p90_brl_per_m2": 7500.0,
                    }
                },
                "by_iptu_pattern_citywide": {},
                "citywide": {
                    "count": 100,
                    "p10_brl_per_m2": 2000.0,
                    "median_brl_per_m2": 4000.0,
                    "p90_brl_per_m2": 9000.0,
                },
            },
        }

        estimate = estimate_reference(reference, 80, "01005", None, True)

        self.assertEqual(estimate["estimated_value_brl"], 400000)
        self.assertEqual(estimate["comparable_support"]["scope"], "cep_prefix5")
        self.assertEqual(estimate["comparable_support"]["transactions"], 35)
        self.assertIsNone(estimate["input"]["iptu_pattern_code"])

    def test_estimate_without_pattern_falls_back_to_citywide_if_cep_support_is_small(self):
        reference = {
            "target": "ITBI declared purchase value",
            "area_basis": "IPTU built area",
            "reference_period": {"start": "2026-01-01", "end": "2026-09-07"},
            "temporal_backtest": {},
            "profiles": {
                "by_cep_prefix5_and_iptu_pattern": {},
                "by_cep_prefix5": {
                    "01005": {
                        "count": 2,
                        "p10_brl_per_m2": 3500.0,
                        "median_brl_per_m2": 5000.0,
                        "p90_brl_per_m2": 7500.0,
                    }
                },
                "by_iptu_pattern_citywide": {},
                "citywide": {
                    "count": 100,
                    "p10_brl_per_m2": 2000.0,
                    "median_brl_per_m2": 4000.0,
                    "p90_brl_per_m2": 9000.0,
                },
            },
        }

        estimate = estimate_reference(reference, 80, "01005", None, True)

        self.assertEqual(estimate["estimated_value_brl"], 320000)
        self.assertEqual(estimate["comparable_support"]["scope"], "citywide")

    @unittest.skipUnless(
        (DATA_DIR / OFFICIAL_FILE).is_file(),
        "Official ITBI workbook is not present in this checkout.",
    )
    def test_source_backtest_is_temporally_held_out_and_meets_reported_shape(self):
        reference = build_reference_rates(DATA_DIR)
        backtest = reference["temporal_backtest"]

        self.assertEqual(reference["reference_period"]["transactions"], 42826)
        self.assertEqual(reference["filter_counts"]["ambiguous_rows_excluded"], 46)
        self.assertEqual(backtest["training_transactions"], 31222)
        self.assertEqual(backtest["test_transactions"], 11394)
        self.assertLess(backtest["median_absolute_percentage_error"], 0.30)
        self.assertLess(backtest["p90_absolute_percentage_error"], 0.80)
        self.assertGreater(backtest["p10_p90_range_coverage"], 0.70)
        self.assertLess(backtest["p10_p90_range_coverage"], 0.90)
        self.assertEqual(
            sum(backtest["test_scope_counts"].values()),
            backtest["test_transactions"],
        )


if __name__ == "__main__":
    unittest.main()
