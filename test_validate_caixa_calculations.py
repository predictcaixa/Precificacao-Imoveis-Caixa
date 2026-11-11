from __future__ import annotations

import copy
import json
import unittest

from scripts.audit_caixa_validation import DEFAULT_INPUT, audit_dataset
from scripts.validate_caixa_calculations import (
    _reference_metrics,
    validate_report,
)


class ValidateCaixaCalculationsTests(unittest.TestCase):
    def test_hand_simulation_matches_expected_error_metrics(self) -> None:
        metrics = _reference_metrics([100, 200, 300], [90, 220, 300])
        self.assertEqual(metrics["mae_brl"], 10)
        self.assertEqual(metrics["rmse_brl"], 12.91)
        self.assertEqual(metrics["median_absolute_percentage_error_percent"], 10)
        self.assertEqual(metrics["p90_absolute_percentage_error_percent"], 10)
        self.assertEqual(metrics["wape_percent"], 5)
        self.assertEqual(metrics["smape_percent"], 6.6834)
        self.assertEqual(metrics["r2"], 0.975)

    def test_independent_recalculation_passes_for_received_caixa_batch(self) -> None:
        audit = audit_dataset(DEFAULT_INPUT)
        result = validate_report(DEFAULT_INPUT, audit)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["checks_failed"], 0)
        self.assertGreaterEqual(result["checks_passed"], 40)

    def test_independent_recalculation_detects_corrupted_metric(self) -> None:
        audit = audit_dataset(DEFAULT_INPUT)
        changed = copy.deepcopy(audit)
        changed["spatial_baseline_validation"]["estimators"][
            "training_citywide_median"
        ]["out_of_fold_metrics"]["mae_brl"] += 1
        result = validate_report(DEFAULT_INPUT, changed)
        self.assertEqual(result["status"], "failed")
        failed_names = {item["check"] for item in result["checks"] if not item["passed"]}
        self.assertIn(
            "spatial_training_citywide_median_mae_brl",
            failed_names,
        )

    def test_validation_output_contains_aggregate_only(self) -> None:
        audit = audit_dataset(DEFAULT_INPUT)
        result = validate_report(DEFAULT_INPUT, audit)
        serialized = json.dumps(result, ensure_ascii=False)
        with DEFAULT_INPUT.open(encoding="utf-8-sig", newline="") as handle:
            import csv

            private_record = next(csv.DictReader(handle))
        for field in ("n_do_imovel", "endereco", "link_de_acesso", "sql_iptu"):
            value = private_record[field].strip()
            if value:
                self.assertNotIn(value, serialized)


if __name__ == "__main__":
    unittest.main()
