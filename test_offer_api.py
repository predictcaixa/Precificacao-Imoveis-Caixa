from __future__ import annotations

import math
import json
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

import main
from scripts import serve_offer_avm
from scripts.serve_offer_avm import (
    AvmModelBundle,
    build_api_feature_row,
    load_avm_model,
    load_avm_models,
    predict_discounted_offer,
    predict_discounted_offers,
)


def sample_input() -> main.AvmApartmentInput:
    return main.AvmApartmentInput(
        area_privativa_m2=60,
        idade_anos=10,
        quartos=2,
        banheiros=2,
        vagas=1,
        elevador=1,
        regiao="zona leste",
        distrito="Cangaíba",
    )


class FixedLogModel:
    def __init__(self) -> None:
        self.received = None

    def predict(self, frame):
        self.received = frame
        return [math.log1p(321000)] * len(frame)


class OfferAvmApiTests(unittest.TestCase):
    def test_root_serves_frontend_and_health_endpoint_remains_available(self):
        frontend = main.serve_frontend()
        self.assertEqual(Path(frontend.path), main.FRONTEND_PATH)
        self.assertEqual(frontend.media_type, "text/html")
        self.assertIn("/health", {route.path for route in main.app.routes})
        self.assertFalse(main.health()["estimativa_operacional_aprovada"])

    def test_api_features_match_model_schema_and_exclude_prices(self):
        features = build_api_feature_row(main.avm_input_as_dict(sample_input()))
        self.assertEqual(features["AREA PRIV."], 60)
        self.assertEqual(features["Região"], "Zona Leste")
        self.assertEqual(features["Distrito"], "Cangaíba")
        self.assertNotIn("VALOR OFERTA", features)
        self.assertNotIn("Valor Venal", features)
        self.assertNotIn("Valor Declarado", features)
        self.assertNotIn("Valor ITBI.", features)

    def test_inference_returns_inverse_log_prediction(self):
        model = FixedLogModel()
        bundle = AvmModelBundle(
            model=model,
            report={"feature_columns": ["AREA PRIV.", "IDADE", "Região", "Distrito"]},
            model_type="random_forest",
        )
        prediction = predict_discounted_offer(
            bundle, main.avm_input_as_dict(sample_input())
        )
        self.assertEqual(prediction, 321000)
        self.assertEqual(list(model.received.columns), bundle.report["feature_columns"])

    def test_batch_inference_predicts_all_rows_in_one_call(self):
        model = FixedLogModel()
        bundle = AvmModelBundle(
            model=model,
            report={"feature_columns": ["AREA PRIV.", "IDADE"]},
            model_type="random_forest",
        )
        predictions = predict_discounted_offers(
            bundle, [main.avm_input_as_dict(sample_input())] * 3
        )
        self.assertEqual(predictions, [321000] * 3)
        self.assertEqual(len(model.received), 3)

    def test_xgboost_artifact_is_supported_by_model_loader(self):
        fake_model = FixedLogModel()
        xgboost_module = types.ModuleType("xgboost")
        joblib_module = types.ModuleType("joblib")
        joblib_module.load = lambda _path: fake_model
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            report_path = root / "avm_report.json"
            report_path.write_text(
                json.dumps(
                    {
                        "status": "experimental_not_operationally_approved",
                        "feature_columns": ["AREA PRIV."],
                        "selected_model": "xgboost_depth_4",
                        "model_file": "models/offer_avm_xgboost.joblib",
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch.object(serve_offer_avm, "BASE_DIR", root),
                patch.dict(
                    "sys.modules",
                    {"xgboost": xgboost_module, "joblib": joblib_module},
                ),
            ):
                bundle = load_avm_model(report_path)
        self.assertIs(bundle.model, fake_model)
        self.assertEqual(bundle.model_type, "xgboost")

    def test_model_loader_keeps_every_trained_artifact_available(self):
        report = {
            "status": "experimental_not_operationally_approved",
            "feature_columns": ["AREA PRIV."],
            "selected_model": "random_forest",
            "available_models": {
                name: {"status": "trained", "candidate": name}
                for name in ("random_forest", "catboost", "xgboost")
            },
        }
        loaded = {}
        def fake_loader(_report, key, _entry):
            bundle = AvmModelBundle(FixedLogModel(), report, key)
            loaded[key] = bundle
            return bundle

        with (
            patch.object(serve_offer_avm, "_read_avm_report", return_value=report),
            patch.object(serve_offer_avm, "_load_model_bundle", side_effect=fake_loader),
        ):
            bundles = load_avm_models(Path("unused.json"))
        self.assertEqual(set(bundles), {"random_forest", "catboost", "xgboost"})
        self.assertEqual(bundles, loaded)

    def test_single_prediction_route_returns_experimental_target(self):
        bundle = SimpleNamespace(
            report={
                "selected_model": "random_forest",
                "target_definition": "90% do preço anunciado",
            }
        )
        with (
            patch.object(main, "avm_bundle", bundle),
            patch("main.predict_discounted_offer", return_value=450000),
        ):
            result = main.predict(sample_input())
        self.assertEqual(result["status"], "experimental")
        self.assertEqual(result["estimativa_alvo_brl"], 450000)
        self.assertIn("não representa", result["aviso"].casefold())

    def test_prediction_route_can_select_a_loaded_model(self):
        bundle = SimpleNamespace(
            model_type="xgboost",
            report={
                "selected_model": "random_forest",
                "target_definition": "90% do preço anunciado",
                "available_models": {
                    "xgboost": {"candidate": "xgboost_depth_4"}
                },
            },
        )
        with (
            patch.object(main, "avm_bundle", None),
            patch.object(main, "avm_bundles", {"xgboost": bundle}),
            patch("main.predict_discounted_offer", return_value=456000) as predict,
        ):
            result = main.predict(sample_input(), modelo="xgboost")
        self.assertEqual(result["modelo"], "xgboost_depth_4")
        self.assertEqual(result["algoritmo"], "xgboost")
        self.assertEqual(result["estimativa_alvo_brl"], 456000)
        self.assertIs(predict.call_args.args[0], bundle)

    def test_batch_route_returns_one_result_per_property(self):
        bundle = SimpleNamespace(
            report={
                "selected_model": "random_forest",
                "target_definition": "90% do preço anunciado",
            }
        )
        with (
            patch.object(main, "avm_bundle", bundle),
            patch("main.predict_discounted_offers", return_value=[450000, 460000]) as predict,
        ):
            result = main.predict_batch([sample_input(), sample_input()])
        self.assertEqual(result["quantidade"], 2)
        self.assertEqual(len(result["estimativas"]), 2)
        self.assertEqual(predict.call_count, 1)

    def test_prediction_route_reports_missing_model(self):
        with patch.object(main, "avm_bundle", None):
            with self.assertRaises(HTTPException) as error:
                main.predict(sample_input())
        self.assertEqual(error.exception.status_code, 503)

    def test_model_info_exposes_avm_operational_metadata(self):
        bundle = SimpleNamespace(
            report={
                "selected_model": "random_forest",
                "target_definition": "90% do preço anunciado",
                "independent_geographic_test_metrics": {"r2": 0.73, "n": 100},
                "selected_model_validation_metrics": {"mae_brl": 120000},
                "independent_test_median_baseline_metrics": {"mae_brl": 380000},
                "status": "experimental_not_operationally_approved",
                "generated_at_utc": "2026-10-31T11:00:00+00:00",
                "partition_counts": {"train": 300, "validation": 100},
                "partition_district_counts": {"train": 10, "validation": 3},
                "catboost_status": "skipped_python_3_15_no_wheel",
                "xgboost_status": "trained",
                "model_status": {
                    "random_forest": "trained",
                    "catboost": "skipped_python_3_15_no_wheel",
                    "xgboost": "trained",
                },
                "validation_metrics_by_model": {
                    "random_forest": {
                        "validation_metrics": {"mae_brl": 120000}
                    },
                    "xgboost": {
                        "validation_metrics": {"mae_brl": 110000}
                    },
                },
                "feature_importance": {"AREA PRIV.": 0.6},
                "geographic_validation_by_region": {"Centro": {"n": 20, "mae_brl": 100000}},
            }
        )
        with (
            patch.object(main, "avm_bundle", bundle),
            patch.object(main, "reference_rates", None),
            patch("main.audit_evaluations_csv", return_value={"candidate_rows_for_expert_review": 0}),
            patch(
                "main.audit_caixa_validation_csv",
                return_value={
                    "candidate_rows_for_spatial_validation": 0,
                    "temporal_validation": {"temporal_validation_possible": False},
                },
            ),
        ):
            result = main.info_modelo()["avm_oferta_experimental"]
        self.assertEqual(result["metricas_teste_geografico"]["r2"], 0.73)
        self.assertEqual(result["metricas_validacao"]["mae_brl"], 120000)
        self.assertEqual(result["contagens_particoes"]["train"], 300)
        self.assertEqual(result["status_catboost"], "skipped_python_3_15_no_wheel")
        self.assertEqual(result["status_xgboost"], "trained")
        self.assertEqual(result["status_modelos"]["xgboost"], "trained")
        self.assertEqual(
            result["comparacao_modelos_validacao"]["xgboost"]["validation_metrics"]["mae_brl"],
            110000,
        )
        self.assertEqual(result["importancia_variaveis"]["AREA PRIV."], 0.6)
        self.assertEqual(result["metricas_por_regiao"]["Centro"]["n"], 20)

    def test_input_rejects_fiscal_value_fields(self):
        with self.assertRaises(ValidationError):
            main.AvmApartmentInput(
                area_privativa_m2=60,
                idade_anos=10,
                quartos=2,
                banheiros=2,
                valor_venal=500000,
            )

    def test_input_normalizes_region_and_cep(self):
        request = main.AvmApartmentInput(
            area_privativa_m2=60,
            idade_anos=10,
            quartos=2,
            banheiros=2,
            regiao="Zona Leste²",
            cep="01005-020",
        )
        self.assertEqual(request.regiao, "Zona Leste²")
        self.assertEqual(request.cep, "01005020")

    def test_room_features_can_be_missing_for_model_imputation(self):
        request = main.AvmApartmentInput(
            area_privativa_m2=60,
            idade_anos=10,
        )
        self.assertIsNone(request.quartos)
        self.assertIsNone(request.banheiros)

    def test_import_routes_persist_rows_and_support_history_deletion(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "uploads.sqlite3"
            with patch.object(main.offer_avm_store, "DATABASE_PATH", database_path):
                main.offer_avm_store.initialize_store()
                created = main.create_avm_import(
                    main.AvmImportCreateInput(
                        file_name="apartamentos.xlsx",
                        model="xgboost",
                        total_rows=1,
                    )
                )
                saved = main.append_avm_import_rows(
                    created["id"],
                    [
                        main.AvmImportRowInput(
                            source_row=2,
                            source_data={"AREA PRIV.": 60, "Valor ITBI.": 400000},
                            prediction=450000,
                            status="estimado · experimental",
                        )
                    ],
                )
                finished = main.finish_avm_import(
                    created["id"], main.AvmImportFinishInput(status="completed")
                )
                history = main.get_avm_imports(limit=50)
                stored_rows = main.get_avm_import_rows(
                    created["id"], offset=0, limit=500
                )
                deleted = main.remove_avm_import(created["id"])

        self.assertEqual(saved["saved_rows"], 1)
        self.assertEqual(finished["status"], "completed")
        self.assertIn(history["database"], {"postgresql", "sqlite"})
        self.assertEqual(history["imports"][0]["predicted_rows"], 1)
        self.assertEqual(history["imports"][0]["processed_rows"], 1)
        self.assertEqual(
            stored_rows["rows"][0]["source_data"]["Valor ITBI."], 400000
        )
        self.assertTrue(deleted["deleted"])


if __name__ == "__main__":
    unittest.main()
