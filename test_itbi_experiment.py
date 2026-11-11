from __future__ import annotations

import unittest

from scripts.train_itbi_experiment import _build_model, _estimate, train_experiment


class ItbiExperimentTests(unittest.TestCase):
    def test_segmented_estimator_uses_area_and_falls_back_without_leakage(self) -> None:
        records = []
        for index in range(35):
            records.append(
                {
                    "price_per_m2": 5000.0 + index,
                    "area": 80.0,
                    "iptu_pattern_code": "22",
                    "cep_prefix5": "01005",
                }
            )
        model = _build_model(records)
        probe = {
            "area": 100.0,
            "iptu_pattern_code": "22",
            "cep_prefix5": "01005",
        }
        estimate, scope = _estimate(model, probe, "cep_pattern_median")
        self.assertEqual(scope, "cep_prefix5_and_iptu_pattern")
        self.assertEqual(estimate, 501700.0)
        probe["cep_prefix5"] = "99999"
        estimate, scope = _estimate(model, probe, "cep_pattern_median")
        self.assertEqual(scope, "iptu_pattern_fallback")
        self.assertEqual(estimate, 501700.0)

    def test_experiment_is_temporally_held_out_and_never_enables_appraisal(self) -> None:
        artifact = train_experiment()
        policy = artifact["training_policy"]
        self.assertEqual(artifact["status"], "experimental_itbi_transaction_only_not_an_appraisal")
        self.assertEqual(policy["training_rows"], 31222)
        self.assertEqual(policy["test_rows"], 11394)
        self.assertFalse(policy["test_data_used_for_training"])
        self.assertFalse(artifact["release_decision"]["appraisal_training_enabled"])
        self.assertFalse(artifact["release_decision"]["operational_prediction_enabled"])
        self.assertGreater(
            artifact["target_quality"]["test"]["one_cent_value_count"], 0
        )
        self.assertIn("MAPE", artifact["target_quality"]["note"])
        self.assertIn("global_median", artifact["estimators"])
        self.assertIn("pattern_median", artifact["estimators"])
        self.assertIn("cep_pattern_median", artifact["estimators"])
        self.assertIn(
            "smape_percent",
            artifact["estimators"]["cep_pattern_median"]["test_metrics"],
        )


if __name__ == "__main__":
    unittest.main()
