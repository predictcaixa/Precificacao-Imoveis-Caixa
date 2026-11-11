"""Train and temporally evaluate a separate experimental model for ITBI values."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__:
    from .experimental_reference import DATA_DIR, MIN_COMPARABLES, _eligible_records
    from .audit_data_sources import OFFICIAL_FILE
else:
    from experimental_reference import DATA_DIR, MIN_COMPARABLES, _eligible_records
    from audit_data_sources import OFFICIAL_FILE


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = BASE_DIR / "models" / "itbi_transaction_experiment.json"
TRAINING_CUTOFF_MONTH = 6
TEST_START_MONTH = 7
MODEL_ID = "itbi-declared-transaction-median-cep-pattern-v1"


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    return ordered[int((len(ordered) - 1) * probability)]


def _median(values: list[float]) -> float:
    return _quantile(values, 0.5)


def _build_model(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_pattern: dict[str, list[float]] = defaultdict(list)
    by_cep_pattern: dict[str, list[float]] = defaultdict(list)
    rates: list[float] = []
    for row in records:
        rate = row["price_per_m2"]
        pattern = row["iptu_pattern_code"]
        by_pattern[pattern].append(rate)
        rates.append(rate)
        if row["cep_prefix5"]:
            by_cep_pattern[f"{row['cep_prefix5']}|{pattern}"].append(rate)
    return {
        "global_median_brl_per_m2": _median(rates),
        "by_pattern": {
            key: {
                "count": len(values),
                "median_brl_per_m2": _median(values),
            }
            for key, values in sorted(by_pattern.items())
        },
        "by_cep_prefix5_and_pattern": {
            key: {
                "count": len(values),
                "median_brl_per_m2": _median(values),
            }
            for key, values in sorted(by_cep_pattern.items())
        },
    }


def _estimate(
    model: dict[str, Any], row: dict[str, Any], segmentation: str
) -> tuple[float, str]:
    if segmentation == "global_median":
        return (
            model["global_median_brl_per_m2"] * row["area"],
            "citywide",
        )

    pattern = row["iptu_pattern_code"]
    if segmentation == "pattern_median":
        profile = model["by_pattern"].get(pattern)
        if profile and profile["count"] >= MIN_COMPARABLES:
            return profile["median_brl_per_m2"] * row["area"], "iptu_pattern"
        return model["global_median_brl_per_m2"] * row["area"], "citywide_fallback"

    key = f"{row['cep_prefix5']}|{pattern}"
    profile = model["by_cep_prefix5_and_pattern"].get(key)
    if profile and profile["count"] >= MIN_COMPARABLES:
        return (
            profile["median_brl_per_m2"] * row["area"],
            "cep_prefix5_and_iptu_pattern",
        )
    pattern_profile = model["by_pattern"].get(pattern)
    if pattern_profile and pattern_profile["count"] >= MIN_COMPARABLES:
        return pattern_profile["median_brl_per_m2"] * row["area"], "iptu_pattern_fallback"
    return model["global_median_brl_per_m2"] * row["area"], "citywide_fallback"


def _metrics(actuals: list[float], predictions: list[float]) -> dict[str, float]:
    absolute_errors = [abs(actual - pred) for actual, pred in zip(actuals, predictions)]
    percentage_errors = [
        error / actual for error, actual in zip(absolute_errors, actuals) if actual > 0
    ]
    mean_actual = sum(actuals) / len(actuals)
    total_sum_squares = sum((actual - mean_actual) ** 2 for actual in actuals)
    residual_sum_squares = sum(
        (actual - pred) ** 2 for actual, pred in zip(actuals, predictions)
    )
    wape_denominator = sum(actuals)
    return {
        "mae_brl": round(sum(absolute_errors) / len(absolute_errors), 2),
        "rmse_brl": round(
            math.sqrt(sum(error**2 for error in absolute_errors) / len(absolute_errors)),
            2,
        ),
        "mape_percent": round(
            sum(percentage_errors) / len(percentage_errors) * 100, 4
        ),
        "smape_percent": round(
            sum(
                200 * error / (abs(actual) + abs(prediction))
                for error, actual, prediction in zip(
                    absolute_errors, actuals, predictions
                )
                if abs(actual) + abs(prediction) > 0
            )
            / len(actuals),
            4,
        ),
        "wape_percent": round(
            sum(absolute_errors) / wape_denominator * 100, 4
        ),
        "median_absolute_percentage_error_percent": round(
            _quantile(percentage_errors, 0.5) * 100, 4
        ),
        "p90_absolute_percentage_error_percent": round(
            _quantile(percentage_errors, 0.9) * 100, 4
        ),
        "r2": round(
            1 - residual_sum_squares / total_sum_squares
            if total_sum_squares
            else 0,
            6,
        ),
    }


def _target_quality_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    prices = sorted(row["price"] for row in records)
    return {
        "min_brl": round(prices[0], 2),
        "p01_brl": round(_quantile(prices, 0.01), 2),
        "median_brl": round(_median(prices), 2),
        "max_brl": round(prices[-1], 2),
        "below_1000_brl_count": sum(price < 1000 for price in prices),
        "below_1000_brl_share_percent": round(
            sum(price < 1000 for price in prices) / len(prices) * 100, 4
        ),
        "one_cent_value_count": sum(price == 0.01 for price in prices),
    }


def _source_sha256(source_path: Path) -> str:
    digest = hashlib.sha256()
    with source_path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def train_experiment(data_dir: Path = DATA_DIR) -> dict[str, Any]:
    records, filter_counts = _eligible_records(data_dir)
    training = [
        row for row in records if int(row["date"][5:7]) <= TRAINING_CUTOFF_MONTH
    ]
    training_sql = {row["sql"] for row in training}
    test_candidates = [
        row for row in records if int(row["date"][5:7]) >= TEST_START_MONTH
    ]
    test = [row for row in test_candidates if row["sql"] not in training_sql]
    excluded_repeated_sql = len(test_candidates) - len(test)
    if not training or not test:
        raise ValueError("Dados insuficientes para divisão temporal do experimento ITBI.")

    model = _build_model(training)
    estimators = {
        "global_median": "Mediana global do valor declarado por m².",
        "pattern_median": (
            "Mediana por código de padrão IPTU; fallback para mediana municipal."
        ),
        "cep_pattern_median": (
            "Mediana por prefixo de CEP + código de padrão IPTU; "
            "fallback por padrão IPTU e depois municipal."
        ),
    }
    metrics: dict[str, Any] = {}
    for estimator, description in estimators.items():
        predictions: list[float] = []
        actuals: list[float] = []
        scope_counts: Counter[str] = Counter()
        for row in test:
            prediction, scope = _estimate(model, row, estimator)
            predictions.append(prediction)
            actuals.append(row["price"])
            scope_counts[scope] += 1
        metrics[estimator] = {
            "description": description,
            "test_metrics": _metrics(actuals, predictions),
            "test_scope_counts": dict(sorted(scope_counts.items())),
        }

    source_path = data_dir / OFFICIAL_FILE
    test_dates = sorted(row["date"] for row in test)
    training_dates = sorted(row["date"] for row in training)
    return {
        "experiment_version": 1,
        "model_id": MODEL_ID,
        "status": "experimental_itbi_transaction_only_not_an_appraisal",
        "target": {
            "name": "ITBI declared transaction value",
            "definition": (
                "Valor da transação declarado pelo contribuinte na compra e venda "
                "com transmissão integral."
            ),
            "unit": "BRL",
            "not_equivalent_to": [
                "appraisal_value",
                "tax_reference_value",
                "tax_calculation_base",
                "asking_price",
            ],
        },
        "features": [
            {
                "name": "built_area_iptu_m2",
                "definition": "Área Construída cadastral IPTU em m².",
                "use": "Multiplica a mediana do preço declarado por m².",
            },
            {
                "name": "iptu_pattern_code",
                "definition": "Código categórico do Padrão IPTU.",
                "use": "Segmentação de comparáveis; não interpretado como padrão IBAPE.",
            },
            {
                "name": "cep_prefix5",
                "definition": "Cinco primeiros dígitos do CEP cadastral.",
                "use": "Segmentação local quando há suporte mínimo.",
            },
        ],
        "training_policy": {
            "record_filters": filter_counts,
            "training_rows": len(training),
            "training_period": {
                "start": training_dates[0],
                "end": training_dates[-1],
            },
            "test_rows": len(test),
            "test_period": {"start": test_dates[0], "end": test_dates[-1]},
            "test_rows_excluded_for_sql_seen_in_training": excluded_repeated_sql,
            "minimum_comparables_per_segment": MIN_COMPARABLES,
            "test_data_used_for_training": False,
        },
        "target_quality": {
            "training": _target_quality_summary(training),
            "test": _target_quality_summary(test),
            "note": (
                "Valores positivos muito baixos foram mantidos por não haver regra "
                "documentada que autorize excluí-los. MAPE é extremamente sensível "
                "a esses denominadores; revisar os casos com a fonte antes de qualquer "
                "decisão de uso."
            ),
        },
        "source": {
            "file": OFFICIAL_FILE,
            "sheet": "2026",
            "sha256": _source_sha256(source_path),
            "source_period": {
                "start": min(row["date"] for row in records),
                "end": max(row["date"] for row in records),
            },
        },
        "estimators": metrics,
        "fitted_parameters": model,
        "release_decision": {
            "appraisal_training_enabled": False,
            "operational_prediction_enabled": False,
            "reason": (
                "Este experimento aprende somente valores declarados ITBI. "
                "Não valida avaliação imobiliária nem é candidato a uso operacional CAIXA."
            ),
        },
        "limitations": [
            "O valor ITBI é declarado pelo contribuinte, não um laudo de avaliação.",
            "O teste é temporal e provém da mesma fonte administrativa; não é validação independente de avaliação.",
            "A área construída IPTU não é tratada como área privativa ou total.",
            "Os códigos de padrão IPTU não são convertidos em classes IBAPE.",
            "Os resultados não devem ser usados em crédito, garantia, laudo ou decisão operacional.",
        ],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    artifact = train_experiment(args.data_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Experimento ITBI gerado: {args.output}; "
        f"treino={artifact['training_policy']['training_rows']}; "
        f"teste={artifact['training_policy']['test_rows']}; "
        "avaliacao_operacional=False"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
