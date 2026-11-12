"""Compare the hedonic challenger and System 1 on the same held-out districts."""

from __future__ import annotations

import csv
import hashlib
import json
import statistics
import sys
from pathlib import Path
from typing import Any

import joblib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.serve_offer_avm import (
    load_avm_model,
    predict_discounted_offers,
)
from scripts.train_hedonic_avm import (
    DEFAULT_INPUT,
    DEFAULT_OUTPUT_DIR,
    RANDOM_STATE,
    _predict as predict_hedonic,
)
from scripts.train_offer_avm import (
    BASE_DIR,
    SHEET_NAME,
    _frame,
    _grouped_split,
    calculate_metrics,
    iter_xlsx_rows,
    prepare_training_records,
)


SYSTEM1_REPORT = BASE_DIR / "models" / "offer_avm" / "avm_report.json"
SYSTEM2_ARTIFACT = DEFAULT_OUTPUT_DIR / "hedonic_spline_ridge.joblib"
SYSTEM2_REPORT = DEFAULT_OUTPUT_DIR / "report.json"
OUTPUT_JSON = BASE_DIR / "dados" / "derivados" / "comparacao_system2_v2_vs_system1.json"
OUTPUT_CSV = BASE_DIR / "dados" / "derivados" / "comparacao_system2_v2_vs_system1.csv"


def _json_default(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"Tipo não serializável no relatório: {type(value).__name__}")


def _api_input(features: dict[str, Any]) -> dict[str, Any]:
    return {
        "latitude": features["LATITUDE"],
        "longitude": features["LONGITUDE"],
        "idade_anos": features["IDADE"],
        "quartos": features["QUARTOS"],
        "banheiros": features["BANHEIROS"],
        "vagas": features["VAGAS"],
        "elevador": features["ELEVADOR"],
        "renda_mediana_mensal_brl": features["RENDA MEDIANA IBGE 2022 (R$)"],
        "renda_media_mensal_brl": features["RENDA MÉDIA IBGE 2022 (R$)"],
        "area_total_m2": features["Área total"],
        "area_privativa_m2": features["AREA PRIV."],
        "cep": features["CEP"],
        "regiao": features["Região"],
        "distrito": features["Distrito"],
        "setor_censitario": features["SETOR CENSITÁRIO 2022"],
        "padrao_iptu": features["Padrão (IPTU)"],
    }


def _paired_summary(actual: list[float], challenger: list[float], baseline: list[float]) -> dict[str, Any]:
    challenger_errors = [abs(pred - truth) for truth, pred in zip(actual, challenger)]
    baseline_errors = [abs(pred - truth) for truth, pred in zip(actual, baseline)]
    gaps = [abs(left - right) for left, right in zip(challenger, baseline)]
    wins = sum(a < b for a, b in zip(challenger_errors, baseline_errors))
    losses = sum(a > b for a, b in zip(challenger_errors, baseline_errors))
    ties = len(actual) - wins - losses
    return {
        "challenger_lower_absolute_error_rows": wins,
        "system1_lower_absolute_error_rows": losses,
        "ties": ties,
        "challenger_win_share_percent": round(wins * 100 / len(actual), 2),
        "median_absolute_prediction_gap_brl": round(statistics.median(gaps), 2),
        "p90_absolute_prediction_gap_brl": round(sorted(gaps)[int(0.9 * (len(gaps) - 1))], 2),
        "maximum_absolute_prediction_gap_brl": round(max(gaps), 2),
    }


def run() -> dict[str, Any]:
    rows = list(iter_xlsx_rows(DEFAULT_INPUT, SHEET_NAME, include_source_row=True))
    records, audit = prepare_training_records(rows)
    partitions = _grouped_split(records, RANDOM_STATE)
    test = partitions["independent_geographic_test"]
    actual = [float(record["target"]) for record in test]
    property_inputs = [_api_input(record["features"]) for record in test]

    system1_catboost = load_avm_model(SYSTEM1_REPORT, "catboost")
    system1_xgboost = load_avm_model(SYSTEM1_REPORT, "xgboost")
    catboost_predictions = predict_discounted_offers(system1_catboost, property_inputs)
    xgboost_predictions = predict_discounted_offers(system1_xgboost, property_inputs)

    challenger_bundle = joblib.load(SYSTEM2_ARTIFACT)
    challenger_report = json.loads(SYSTEM2_REPORT.read_text(encoding="utf-8"))
    if challenger_bundle.get("model_id") != "hedonic_spline_ridge_v2":
        raise ValueError("O artefato não corresponde ao challenger hedônico esperado.")
    hedonic_predictions = predict_hedonic(
        challenger_bundle["model"],
        float(challenger_bundle["smearing_factor"]),
        test,
        challenger_bundle["feature_names"],
    )

    metrics = {
        "system1_default_catboost": calculate_metrics(actual, catboost_predictions),
        "system1_validation_selected_xgboost": calculate_metrics(actual, xgboost_predictions),
        "system2_hedonic_spline_ridge": calculate_metrics(actual, hedonic_predictions),
    }
    comparisons = {
        "system2_vs_system1_catboost": _paired_summary(
            actual, hedonic_predictions, catboost_predictions
        ),
        "system2_vs_system1_xgboost": _paired_summary(
            actual, hedonic_predictions, xgboost_predictions
        ),
    }

    output_rows = []
    for record, truth, cat_pred, xgb_pred, hedonic_pred in zip(
        test, actual, catboost_predictions, xgboost_predictions, hedonic_predictions
    ):
        output_rows.append({
            "source_excel_row": record["source_row"],
            "distrito": record["district"],
            "alvo_90pct_oferta_brl": round(truth, 2),
            "system1_catboost_brl": round(cat_pred, 2),
            "system1_xgboost_brl": round(xgb_pred, 2),
            "system2_hedonic_ridge_brl": round(hedonic_pred, 2),
            "erro_abs_catboost_brl": round(abs(cat_pred - truth), 2),
            "erro_abs_xgboost_brl": round(abs(xgb_pred - truth), 2),
            "erro_abs_hedonic_brl": round(abs(hedonic_pred - truth), 2),
            "diferenca_hedonic_menos_catboost_brl": round(hedonic_pred - cat_pred, 2),
            "diferenca_hedonic_menos_xgboost_brl": round(hedonic_pred - xgb_pred, 2),
        })

    system1_report = json.loads(SYSTEM1_REPORT.read_text(encoding="utf-8"))
    source_hash = hashlib.sha256(DEFAULT_INPUT.read_bytes()).hexdigest()
    residual_path = BASE_DIR / system1_report["test_residuals_file"]
    with residual_path.open("r", newline="", encoding="utf-8-sig") as handle:
        system1_test_rows = {
            row["source_excel_row"]: row for row in csv.DictReader(handle)
        }
    matched_test_rows = [
        record for record in test
        if str(record["source_row"]) in system1_test_rows
        and abs(
            float(record["target"])
            - float(system1_test_rows[str(record["source_row"])]["target_brl"])
        ) < 0.01
        and record["district"]
        == system1_test_rows[str(record["source_row"])]["district"]
    ]
    if len(matched_test_rows) != len(test) or len(system1_test_rows) != len(test):
        raise ValueError(
            "O holdout atual não coincide linha a linha com os resíduos independentes do Sistema 1."
        )
    source_hash_matches = system1_report.get("source_sha256") == source_hash

    report = {
        "comparison_id": "system2_hedonic_v2_vs_system1_2026-11-11",
        "generated_from": str(DEFAULT_INPUT.relative_to(BASE_DIR)),
        "source_sha256": source_hash,
        "target": "90% da oferta; proxy, não venda confirmada nem avaliação CAIXA",
        "test_design": {
            "method": "mesma divisão geográfica estratificada por distrito dos dois treinamentos",
            "random_state": RANDOM_STATE,
            "test_rows": len(test),
            "test_districts": len({record["district"] for record in test}),
            "eligible_rows": len(records),
            "partition_counts": {name: len(part) for name, part in partitions.items()},
            "source_row_overlap_between_test_and_development": False,
            "source_workbook_hash_matches_system1_training": source_hash_matches,
            "verified_against_system1_test_residuals": {
                "matched_source_rows_with_same_target_and_district": len(matched_test_rows),
                "total_system1_test_residual_rows": len(system1_test_rows),
            },
        },
        "models": {
            "system1_production_configured_default": "CatBoost",
            "system1_validation_selected_candidate": system1_report.get("selected_model"),
            "system2": challenger_report.get("model_id"),
        },
        "metrics_on_same_test_rows": metrics,
        "paired_comparisons": comparisons,
        "data_audit": audit,
        "interpretation": [
            "Comparação feita contra o alvo proxy 90% da oferta, não contra valores de venda ou avaliação independente.",
            "As métricas são comparáveis porque foram calculadas nas mesmas linhas e com a mesma divisão geográfica.",
            "O resultado não habilita uso operacional nem escolhe modelo para avaliação CAIXA.",
        ],
        "row_results_csv": str(OUTPUT_CSV.relative_to(BASE_DIR)),
    }

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output_rows[0]))
        writer.writeheader()
        writer.writerows(output_rows)
    return report


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2, default=_json_default))
