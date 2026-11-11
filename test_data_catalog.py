from __future__ import annotations

import unittest

from scripts.build_data_catalog import build_catalog


class DataCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = build_catalog()
        cls.datasets = {item["id"]: item for item in cls.catalog["datasets"]}

    def test_targets_are_separated_and_training_is_not_released(self) -> None:
        self.assertFalse(self.catalog["summary"]["training_enabled"])
        self.assertEqual(
            self.datasets["itbi_pmsp_transactions"]["data_kind"], "transaction"
        )
        self.assertEqual(
            self.datasets["asking_price_offers"]["data_kind"], "asking_price_offer"
        )
        self.assertEqual(
            self.datasets["evaluation_labels"]["data_kind"], "appraisal"
        )
        self.assertEqual(
            self.datasets["experimental_itbi_transaction_model"]["data_kind"],
            "experimental_declared_transaction_model",
        )
        self.assertEqual(
            self.datasets["experimental_itbi_transaction_model"]["status"],
            "experimental_itbi_transaction_only_not_an_appraisal",
        )
        self.assertEqual(
            self.catalog["summary"]["itbi_experiment_test_rows"], 11394
        )
        self.assertIn(
            "cep_pattern_median",
            self.catalog["summary"]["itbi_experiment_estimators"],
        )
        self.assertNotEqual(
            self.datasets["itbi_pmsp_transactions"]["target"],
            self.datasets["evaluation_labels"]["target"],
        )

    def test_existing_appraisal_and_offer_templates_are_empty(self) -> None:
        self.assertTrue(self.datasets["evaluation_labels"]["exists"])
        self.assertTrue(self.datasets["asking_price_offers"]["exists"])
        self.assertEqual(self.catalog["summary"]["appraisal_label_rows"], 0)
        self.assertEqual(self.catalog["summary"]["offer_rows"], 0)

    def test_caixa_validation_candidate_is_cataloged_without_releasing_training(self) -> None:
        audit = self.datasets["caixa_sp_validation_candidate"]["audit_status"]
        self.assertEqual(audit["record_count"], 480)
        self.assertEqual(audit["candidate_rows_for_spatial_validation"], 478)
        self.assertEqual(
            audit["temporal_validation"]["status"],
            "blocked_missing_appraisal_date",
        )
        self.assertFalse(audit["release_decision"]["appraisal_training_enabled"])
        self.assertFalse(self.catalog["summary"]["training_enabled"])
        self.assertEqual(
            self.catalog["summary"]["caixa_calculation_validation_status"],
            "passed",
        )
        self.assertGreaterEqual(
            self.catalog["summary"]["caixa_calculation_checks_passed"],
            90,
        )
        self.assertEqual(
            self.catalog["summary"]["caixa_calculation_checks_failed"],
            0,
        )

    def test_source_metadata_contains_reproducible_hashes(self) -> None:
        source = self.datasets["itbi_pmsp_transactions"]
        self.assertTrue(source["exists"])
        self.assertEqual(len(source["sha256"]), 64)
        self.assertGreater(source["size_bytes"], 0)

    def test_join_counts_match_audit(self) -> None:
        self.assertEqual(self.catalog["summary"]["enriched_join_unique"], 9658)
        self.assertEqual(self.catalog["summary"]["enriched_join_ambiguous"], 2)


if __name__ == "__main__":
    unittest.main()
