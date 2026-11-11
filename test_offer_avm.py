from __future__ import annotations

import unittest

from scripts.train_offer_avm import (
    EXCLUDED_PRICE_AND_ID_COLUMNS,
    FEATURE_ALLOWLIST,
    TARGET_COLUMN,
    calculate_metrics,
    prepare_training_records,
    select_feature_columns,
    _grouped_split,
    _best_validation_metrics_by_model,
)


def sample_row(**overrides: str) -> dict[str, str]:
    row = {
        "0,90*OFERTA": "450000",
        "VALOR OFERTA": "500000",
        "IDADE": "10",
        "AREA PRIV.": "60",
        "LATITUDE": "-23.5",
        "LONGITUDE": "-46.6",
        "QUARTOS": "2",
        "BANHEIROS": "2",
        "VAGAS": "1",
        "ELEVADOR": "1",
        "Padrão (IPTU)": "22",
        "RENDA MEDIANA IBGE 2022 (R$)": "5000",
        "RENDA MÉDIA IBGE 2022 (R$)": "7000",
        "Área total": "75",
        "CEP": "01000000",
        "Região": "",
        "Distrito": "Distrito A",
        "SETOR CENSITÁRIO 2022": "",
        "(SQL)": "123",
        "_source_excel_row": "2",
        "Valor Venal": "900000",
        "Valor Declarado": "850000",
        "Valor ITBI.": "850000",
    }
    row.update(overrides)
    return row


class OfferAvmPipelineTests(unittest.TestCase):
    def test_features_use_explicit_allowlist_and_never_include_price_fields(self):
        records, _ = prepare_training_records(
            [
                sample_row(**{"Distrito": "Distrito A"}),
                sample_row(**{"Distrito": "Distrito B", "LATITUDE": "-23.6"}),
            ]
        )
        numeric, categorical = select_feature_columns(records)
        features = set(numeric + categorical)
        self.assertTrue(features <= set(FEATURE_ALLOWLIST))
        self.assertFalse(features & set(EXCLUDED_PRICE_AND_ID_COLUMNS))
        self.assertEqual(len(features), len(numeric) + len(categorical))
        self.assertNotIn(TARGET_COLUMN, features)
        self.assertNotIn("VALOR OFERTA", features)
        self.assertNotIn("Valor Venal", features)
        self.assertNotIn("Valor Declarado", features)
        self.assertNotIn("Valor ITBI.", features)

    def test_training_filters_age_area_and_invalid_target(self):
        rows = [
            sample_row(),
            sample_row(**{"IDADE": "21", "_source_excel_row": "3"}),
            sample_row(**{"AREA PRIV.": "34", "_source_excel_row": "4"}),
            sample_row(**{"0,90*OFERTA": "0", "_source_excel_row": "5"}),
        ]
        records, report = prepare_training_records(rows)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["target"], 450000)
        self.assertEqual(report["excluded_rows_by_reason"]["age_over_20_years"], 1)
        self.assertEqual(
            report["excluded_rows_by_reason"]["private_area_missing_or_out_of_range"],
            1,
        )
        self.assertEqual(
            report["excluded_rows_by_reason"]["target_missing_or_nonpositive"], 1
        )

    def test_discount_mismatch_is_excluded_and_reported(self):
        records, report = prepare_training_records(
            [sample_row(**{"0,90*OFERTA": "470000"})]
        )
        self.assertEqual(records, [])
        self.assertEqual(report["rows_with_offer_discount_mismatch"], 1)
        self.assertEqual(
            report["excluded_rows_by_reason"][
                "target_not_equal_to_90_percent_of_offer"
            ],
            1,
        )

    def test_missing_original_offer_is_not_used_as_a_discounted_label(self):
        records, report = prepare_training_records(
            [sample_row(**{"VALOR OFERTA": ""})]
        )
        self.assertEqual(records, [])
        self.assertEqual(report["target_rows_without_valid_offer"], 1)

    def test_extreme_feature_values_are_missing_not_silently_clipped(self):
        records, report = prepare_training_records(
            [sample_row(**{"QUARTOS": "41"})]
        )
        self.assertIsNone(records[0]["features"]["QUARTOS"])
        self.assertEqual(
            report["feature_values_out_of_range_set_to_missing"]["QUARTOS"], 1
        )

    def test_metrics_use_percentage_units_for_mape(self):
        metrics = calculate_metrics([100, 200], [90, 220])
        self.assertAlmostEqual(metrics["mae_brl"], 15)
        self.assertAlmostEqual(metrics["rmse_brl"], (250**0.5))
        self.assertAlmostEqual(metrics["mape_percent"], 10)
        self.assertAlmostEqual(metrics["r2"], 0.9)

    def test_validation_comparison_keeps_best_candidate_for_each_model(self):
        comparison = _best_validation_metrics_by_model(
            [
                {
                    "name": "random_forest",
                    "kind": "random_forest",
                    "parameters": {"n_estimators": 300},
                    "validation_metrics": {"mae_brl": 100},
                },
                {
                    "name": "xgboost_depth_4",
                    "kind": "xgboost",
                    "parameters": {"max_depth": 4},
                    "validation_metrics": {"mae_brl": 90},
                },
                {
                    "name": "xgboost_depth_6",
                    "kind": "xgboost",
                    "parameters": {"max_depth": 6},
                    "validation_metrics": {"mae_brl": 80},
                },
            ]
        )
        self.assertEqual(comparison["random_forest"]["candidate_count"], 1)
        self.assertEqual(comparison["xgboost"]["candidate"], "xgboost_depth_6")
        self.assertEqual(comparison["xgboost"]["candidate_count"], 2)

    def test_geographic_partitions_keep_districts_separate_and_cover_regions(self):
        records = [
            {"district": f"district-{region}-{index}", "region": region}
            for region in ("north", "south", "east", "west", "center")
            for index in range(6)
        ]
        partitions = _grouped_split(records, random_state=42)
        district_sets = {
            name: {record["district"] for record in rows}
            for name, rows in partitions.items()
        }
        expected_regions = {record["region"] for record in records}
        for partition in partitions.values():
            self.assertEqual(
                {record["region"] for record in partition}, expected_regions
            )
        self.assertFalse(district_sets["train"] & district_sets["validation"])
        self.assertFalse(
            district_sets["train"] & district_sets["independent_geographic_test"]
        )
        self.assertFalse(
            district_sets["validation"]
            & district_sets["independent_geographic_test"]
        )


if __name__ == "__main__":
    unittest.main()
