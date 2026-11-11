from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from main import (
    CaixaExploratoryEstimateInput,
    audit_caixa_validation_labels,
    estimate_caixa_exploratory_endpoint,
    info_modelo,
)
from scripts.audit_caixa_validation import (
    DEFAULT_INPUT,
    _temporal_holdout_validation,
    audit_dataset,
    estimate_caixa_exploratory_reference,
)


class CaixaValidationAuditTests(unittest.TestCase):
    def test_api_exposes_audit_and_keeps_model_suspended(self) -> None:
        audit = audit_caixa_validation_labels()
        info = info_modelo()
        self.assertEqual(audit["record_count"], 480)
        self.assertEqual(
            info["situacao_entregaveis"]["lote_caixa_avaliacoes_candidato"],
            478,
        )
        self.assertFalse(info["situacao_entregaveis"]["validacao_temporal_caixa_possivel"])
        self.assertFalse(info["habilita_predicao"])

    def test_exploratory_caixa_simulation_is_available_but_not_operational(self) -> None:
        result = estimate_caixa_exploratory_endpoint(
            CaixaExploratoryEstimateInput(area_privativa_m2=50)
        )
        self.assertEqual(result["status"], "exploratory_simulation_not_operational")
        self.assertEqual(result["input_area_m2"], 50)
        self.assertGreater(result["estimate_brl"], 0)
        self.assertLess(result["observed_reference_range_brl"]["p10"], result["observed_reference_range_brl"]["p90"])
        self.assertEqual(result["support"]["candidate_records"], 478)
        self.assertFalse(result["operational_prediction_enabled"])
        self.assertEqual(result["appraisal_date_coverage_percent"], 0)
        self.assertIn(
            "não é uma avaliação profissional",
            result["disclaimer"].casefold(),
        )

    def test_exploratory_caixa_simulation_rejects_out_of_range_area(self) -> None:
        with self.assertRaises(ValueError):
            estimate_caixa_exploratory_reference(5)

    def test_received_caixa_file_is_candidate_only_and_date_gap_is_reported(self) -> None:
        report = audit_dataset(DEFAULT_INPUT)
        self.assertEqual(report["record_count"], 480)
        self.assertEqual(report["candidate_rows_for_spatial_validation"], 478)
        self.assertEqual(report["quality"]["appraisal_date_coverage_percent"], 0)
        self.assertFalse(report["temporal_validation"]["temporal_validation_possible"])
        self.assertEqual(
            report["temporal_validation"]["status"],
            "blocked_missing_appraisal_date",
        )
        self.assertEqual(report["quality"]["collection_date_distinct_values"], 1)
        self.assertFalse(report["release_decision"]["appraisal_training_enabled"])
        self.assertFalse(report["release_decision"]["operational_prediction_enabled"])
        self.assertEqual(
            report["feature_incremental_validation"]["status"],
            "exploratory_spatial_feature_ablation",
        )

    def test_spatial_baseline_excludes_leakage_fields_and_identifiers(self) -> None:
        report = audit_dataset(DEFAULT_INPUT)
        baseline = report["spatial_baseline_validation"]
        self.assertTrue(
            any(
                item.startswith("valor_avaliacao_brl_m2")
                for item in baseline["excluded_as_predictors"]
            )
        )
        self.assertTrue(
            any(
                item.startswith("preco_venda_brl")
                for item in baseline["excluded_as_predictors"]
            )
        )
        self.assertEqual(
            sum(fold["test_rows"] for fold in baseline["folds"]),
            baseline["rows_evaluated"],
        )
        self.assertTrue(
            all(fold["neighborhood_overlap"] is False for fold in baseline["folds"])
        )
        serialized = str(report)
        with DEFAULT_INPUT.open(encoding="utf-8-sig", newline="") as handle:
            private_record = next(csv.DictReader(handle))
        self.assertNotIn(private_record["endereco"], serialized)
        self.assertNotIn(private_record["n_do_imovel"], serialized)

    def test_spatial_validation_groups_neighborhoods_without_leakage(self) -> None:
        columns = [
            "n_do_imovel", "cidade", "bairro", "endereco", "tipo",
            "area_ref_m2", "area_tipo", "quartos", "vagas",
            "valor_avaliacao_brl", "avaliacao_brl_m2", "preco_venda_brl",
            "desconto_pct", "modalidade_de_venda", "link_de_acesso",
            "fonte", "natureza_do_valor", "data_coleta", "avaliacao_data",
            "sql_iptu",
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "caixa.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=columns)
                writer.writeheader()
                for group in range(10):
                    writer.writerow(
                        {
                            "n_do_imovel": f"id-{group}",
                            "cidade": "SAO PAULO",
                            "bairro": f"bairro-{group}",
                            "endereco": f"private-{group}",
                            "tipo": "apartamento",
                            "area_ref_m2": "50.0",
                            "area_tipo": "privativa",
                            "quartos": "2",
                            "vagas": "1",
                            "valor_avaliacao_brl": str(250000 + group * 1000),
                            "avaliacao_brl_m2": str((250000 + group * 1000) / 50),
                            "preco_venda_brl": "200000",
                            "desconto_pct": "20",
                            "modalidade_de_venda": "example",
                            "link_de_acesso": "private-link",
                            "fonte": "caixa_lista_imoveis_oficial",
                            "natureza_do_valor": "avaliacao_caixa_imovel_retomado",
                            "data_coleta": "2026-10-26",
                            "avaliacao_data": "",
                            "sql_iptu": "",
                        }
                    )
            report = audit_dataset(path)
        self.assertEqual(report["candidate_rows_for_spatial_validation"], 10)
        self.assertEqual(report["spatial_baseline_validation"]["rows_evaluated"], 10)
        self.assertFalse(report["temporal_validation"]["temporal_validation_possible"])
        self.assertTrue(
            all(not fold["neighborhood_overlap"] for fold in report["spatial_baseline_validation"]["folds"])
        )

    def test_temporal_holdout_uses_appraisal_date_and_excludes_repeated_properties(self) -> None:
        from datetime import date

        records = [
            {
                "appraisal_date": date(2026, 1, index + 1),
                "property_key": f"property-{index}",
                "target": 200000 + index * 1000,
                "area_m2": 50 + index,
            }
            for index in range(10)
        ]
        records.append(
            {
                "appraisal_date": date(2026, 1, 10),
                "property_key": "property-0",
                "target": 210000,
                "area_m2": 50,
            }
        )
        result = _temporal_holdout_validation(records)
        self.assertTrue(result["temporal_validation_possible"])
        self.assertLess(result["training_end_date"], result["test_start_date"])
        self.assertEqual(result["repeated_property_rows_excluded"], 1)
        self.assertEqual(result["test_rows"], 2)


if __name__ == "__main__":
    unittest.main()
