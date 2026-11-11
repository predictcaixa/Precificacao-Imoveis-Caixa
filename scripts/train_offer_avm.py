"""Train and evaluate an experimental AVM on the supplied offer workbook."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__:
    from .audit_data_sources import iter_xlsx_rows
else:
    from audit_data_sources import iter_xlsx_rows


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = BASE_DIR / "dados" / "30.10.2026.xlsx"
DEFAULT_OUTPUT_DIR = BASE_DIR / "models" / "offer_avm"
DEFAULT_WORKBOOK_OUTPUT = (
    BASE_DIR / "dados" / "derivados" / "30.10.2026_avm_estimativas.xlsx"
)
SHEET_NAME = "BASE CONSOLIDADA"
TARGET_COLUMN = "0,90*OFERTA"
OFFER_COLUMN = "VALOR OFERTA"
AGE_COLUMN = "IDADE"
PRIVATE_AREA_COLUMN = "AREA PRIV."
DISTRICT_COLUMN = "Distrito"
REGION_COLUMN = "Região"
RANDOM_STATE = 42

NUMERIC_FEATURES = (
    "LATITUDE",
    "LONGITUDE",
    "IDADE",
    "QUARTOS",
    "BANHEIROS",
    "VAGAS",
    "ELEVADOR",
    "RENDA MEDIANA IBGE 2022 (R$)",
    "RENDA MÉDIA IBGE 2022 (R$)",
    "Área total",
    "AREA PRIV.",
)
CATEGORICAL_FEATURES = (
    "CEP",
    "Região",
    "Distrito",
    "SETOR CENSITÁRIO 2022",
    "Padrão (IPTU)",
)
FEATURE_ALLOWLIST = tuple(dict.fromkeys((*NUMERIC_FEATURES, *CATEGORICAL_FEATURES)))
EXCLUDED_PRICE_AND_ID_COLUMNS = (
    "VALOR OFERTA",
    "0,90*OFERTA",
    "VT BASE",
    "VU BASE",
    "Valor Venal",
    "Valor Declarado",
    "Valor ITBI.",
    "LINK",
    "%",
    "BASE",
    "(SQL)",
    "Matrícula do Imóvel_Cartório de Registro",
    "Endereço",
    "Nº",
    "Complemento",
    "COND",
    "Data de Transação",
    "DT",
    "ACC (IPTU)",
    "ARQUIVO_ORIGEM",
)
OUTPUT_ESTIMATE_COLUMN = "VALOR ESTIMADO AVM"
OUTPUT_STATUS_COLUMN = "STATUS AVM"
MAX_FEATURE_VALUES = {
    "IDADE": 20,
    "QUARTOS": 10,
    "BANHEIROS": 10,
    "VAGAS": 10,
    "ELEVADOR": 1,
}


def parse_number(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        result = float(text)
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def clean_numeric_features(
    row: dict[str, str], invalid_counts: Counter[str] | None = None
) -> dict[str, float | None]:
    cleaned: dict[str, float | None] = {}
    for column in NUMERIC_FEATURES:
        value = parse_number(row.get(column))
        invalid = value is None
        if value is not None:
            if column in MAX_FEATURE_VALUES and not 0 <= value <= MAX_FEATURE_VALUES[column]:
                invalid = True
            elif column == "AREA PRIV." and not 35 <= value <= 1000:
                invalid = True
            elif column == "Área total" and not 0 < value <= 2000:
                invalid = True
            elif column == "LATITUDE" and not -90 <= value <= 90:
                invalid = True
            elif column == "LONGITUDE" and not -180 <= value <= 180:
                invalid = True
            elif column.startswith("RENDA ") and value <= 0:
                invalid = True
            elif column == "Padrão (IPTU)" and value < 0:
                invalid = True
        if invalid and value is not None and invalid_counts is not None:
            invalid_counts[column] += 1
        cleaned[column] = None if invalid else value
    return cleaned


def _category(row: dict[str, str], column: str) -> str:
    return (row.get(column) or "").strip() or "desconhecido"


def _is_in_scope(row: dict[str, str]) -> bool:
    age = parse_number(row.get(AGE_COLUMN))
    area = parse_number(row.get(PRIVATE_AREA_COLUMN))
    return age is not None and 0 <= age <= 20 and area is not None and 35 <= area <= 1000


def build_feature_row(
    row: dict[str, str],
    numeric_invalid_counts: Counter[str] | None = None,
) -> dict[str, Any]:
    features: dict[str, Any] = clean_numeric_features(row, numeric_invalid_counts)
    for column in CATEGORICAL_FEATURES:
        if column == "Padrão (IPTU)":
            value = parse_number(row.get(column))
            features[column] = (
                str(int(value)) if value is not None and value >= 0 else "desconhecido"
            )
        else:
            features[column] = _category(row, column)
    return features


def prepare_training_records(
    rows: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    exclusions: Counter[str] = Counter()
    invalid_features: Counter[str] = Counter()
    eligible: list[dict[str, Any]] = []
    discount_mismatch_count = 0
    missing_offer_count = 0

    for row in rows:
        target = parse_number(row.get(TARGET_COLUMN))
        if target is None or target <= 0:
            exclusions["target_missing_or_nonpositive"] += 1
            continue

        age = parse_number(row.get(AGE_COLUMN))
        if age is None or age < 0:
            exclusions["age_missing_or_invalid"] += 1
            continue
        if age > 20:
            exclusions["age_over_20_years"] += 1
            continue

        area = parse_number(row.get(PRIVATE_AREA_COLUMN))
        if area is None or area < 35 or area > 1000:
            exclusions["private_area_missing_or_out_of_range"] += 1
            continue

        offer = parse_number(row.get(OFFER_COLUMN))
        if offer is None or offer <= 0:
            missing_offer_count += 1
            exclusions["offer_missing_or_nonpositive"] += 1
            continue
        if not math.isclose(target, offer * 0.9, rel_tol=0.005, abs_tol=1):
            discount_mismatch_count += 1
            exclusions["target_not_equal_to_90_percent_of_offer"] += 1
            continue

        feature_values = build_feature_row(row, invalid_features)
        eligible.append(
            {
                "features": feature_values,
                "target": target,
                "district": _category(row, DISTRICT_COLUMN),
                "source_row": row.get("_source_excel_row", ""),
                "region": _category(row, REGION_COLUMN),
            }
        )

    report = {
        "input_rows": len(rows),
        "training_eligible_rows": len(eligible),
        "excluded_rows_by_reason": dict(sorted(exclusions.items())),
        "target_rows_without_valid_offer": missing_offer_count,
        "feature_values_out_of_range_set_to_missing": dict(
            sorted(invalid_features.items())
        ),
        "feature_missing_coverage": {
            name: {
                "count": sum(
                    record["features"][name] is None
                    or record["features"][name] == "desconhecido"
                    for record in eligible
                ),
                "percent": round(
                    100
                    * sum(
                        record["features"][name] is None
                        or record["features"][name] == "desconhecido"
                        for record in eligible
                    )
                    / max(1, len(eligible)),
                    2,
                ),
            }
            for name in FEATURE_ALLOWLIST
        },
        "rows_with_offer_discount_mismatch": discount_mismatch_count,
        "unique_validation_districts": len({item["district"] for item in eligible}),
        "official_region_nonempty_rows": sum(
            item["region"] != "desconhecido" for item in eligible
        ),
    }
    return eligible, report


def select_feature_columns(
    records: list[dict[str, Any]],
) -> tuple[list[str], list[str]]:
    if not records:
        raise ValueError("Não há registros elegíveis para treinamento.")
    numeric = [
        name
        for name in NUMERIC_FEATURES
        if any(record["features"][name] is not None for record in records)
    ]
    categorical = [
        name
        for name in CATEGORICAL_FEATURES
        if len({record["features"][name] for record in records}) > 1
    ]
    selected = set(numeric + categorical)
    forbidden = set(EXCLUDED_PRICE_AND_ID_COLUMNS)
    if selected & forbidden:
        raise ValueError(
            f"Colunas proibidas encontradas nas features: {sorted(selected & forbidden)}"
        )
    if not selected:
        raise ValueError("Nenhuma variável explicativa válida foi encontrada.")
    return numeric, categorical


def calculate_metrics(actual: list[float], predicted: list[float]) -> dict[str, float]:
    if not actual or len(actual) != len(predicted):
        raise ValueError("Métricas exigem vetores não vazios e do mesmo tamanho.")
    errors = [prediction - observed for observed, prediction in zip(actual, predicted)]
    absolute_errors = [abs(error) for error in errors]
    mse = sum(error * error for error in errors) / len(errors)
    actual_mean = sum(actual) / len(actual)
    total_sum_squares = sum((value - actual_mean) ** 2 for value in actual)
    r_squared = (
        1 - sum(error * error for error in errors) / total_sum_squares
        if total_sum_squares > 0
        else 0.0
    )
    return {
        "n": len(actual),
        "r2": r_squared,
        "rmse_brl": math.sqrt(mse),
        "mae_brl": sum(absolute_errors) / len(absolute_errors),
        "mape_percent": (
            100
            * sum(
                absolute / abs(observed)
                for absolute, observed in zip(absolute_errors, actual)
                if observed != 0
            )
        / max(1, sum(value != 0 for value in actual))
        ),
        "bias_brl": sum(errors) / len(errors),
    }


def _iqr_outlier_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    unit_values = sorted(
        record["target"] / record["features"][PRIVATE_AREA_COLUMN]
        for record in records
    )
    if len(unit_values) < 4:
        return {"method": "1.5xIQR", "flagged_rows": 0}
    q1, _, q3 = statistics.quantiles(unit_values, n=4, method="inclusive")
    lower = q1 - 1.5 * (q3 - q1)
    upper = q3 + 1.5 * (q3 - q1)
    return {
        "method": "1.5xIQR on discounted target per private m2",
        "lower_fence_brl_per_m2": lower,
        "upper_fence_brl_per_m2": upper,
        "flagged_rows": sum(value < lower or value > upper for value in unit_values),
        "excluded_automatically": False,
    }


def _report_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(BASE_DIR))
    except ValueError:
        return str(path.resolve())


def _frame(records: list[dict[str, Any]], feature_names: list[str]):
    import pandas as pd

    return pd.DataFrame(
        [{name: record["features"][name] for name in feature_names} for record in records],
        columns=feature_names,
    )


def _grouped_split(records: list[dict[str, Any]], random_state: int):
    from sklearn.model_selection import StratifiedGroupKFold
    import numpy as np

    groups = np.asarray([record["district"] for record in records])
    regions = np.asarray([record["region"] for record in records])
    region_by_district: dict[str, set[str]] = {}
    for district, region in zip(groups, regions):
        region_by_district.setdefault(str(district), set()).add(str(region))
    if any(len(values) != 1 for values in region_by_district.values()):
        raise ValueError("Há distritos associados a mais de uma Região.")
    unique_districts_per_region = Counter(
        region
        for district, region_values in region_by_district.items()
        for region in region_values
    )
    if len(region_by_district) < 10 or min(unique_districts_per_region.values()) < 5:
        raise ValueError(
            "A validação geográfica estratificada requer ao menos 10 distritos e "
            "5 distritos distintos por região."
        )
    outer = StratifiedGroupKFold(
        n_splits=5, shuffle=True, random_state=random_state
    )
    development_idx, test_idx = next(
        outer.split(np.zeros(len(records)), regions, groups=groups)
    )
    development = [records[index] for index in development_idx]
    test = [records[index] for index in test_idx]
    inner = StratifiedGroupKFold(
        n_splits=4, shuffle=True, random_state=random_state + 1
    )
    train_idx, validation_idx = next(
        inner.split(
            np.zeros(len(development)),
            np.asarray([record["region"] for record in development]),
            groups=np.asarray([record["district"] for record in development]),
        )
    )
    train = [development[index] for index in train_idx]
    validation = [development[index] for index in validation_idx]
    partitions = {
        "train": train,
        "validation": validation,
        "independent_geographic_test": test,
    }
    district_sets = {
        name: {record["district"] for record in partition}
        for name, partition in partitions.items()
    }
    if (
        district_sets["train"] & district_sets["validation"]
        or district_sets["train"] & district_sets["independent_geographic_test"]
        or district_sets["validation"] & district_sets["independent_geographic_test"]
    ):
        raise RuntimeError("Vazamento geográfico detectado entre partições.")
    all_regions = {record["region"] for record in records}
    for name, partition in partitions.items():
        if {record["region"] for record in partition} != all_regions:
            raise RuntimeError(
                f"A partição {name} não cobre todas as regiões de treinamento."
            )
    return partitions


def _make_random_forest(numeric_features: list[str], categorical_features: list[str]):
    from sklearn.ensemble import RandomForestRegressor

    return _make_sklearn_pipeline(
        numeric_features,
        categorical_features,
        RandomForestRegressor(
            n_estimators=300,
            max_features=0.8,
            min_samples_leaf=3,
            random_state=RANDOM_STATE,
            n_jobs=-1,
        ),
    )


def _make_sklearn_pipeline(
    numeric_features: list[str],
    categorical_features: list[str],
    estimator: Any,
):
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder

    transformers = []
    if numeric_features:
        numeric_pipeline = Pipeline(
            [("imputer", SimpleImputer(strategy="median", add_indicator=True))]
        )
        transformers.append(("numeric", numeric_pipeline, numeric_features))
    if categorical_features:
        category_pipeline = Pipeline(
            [
                (
                    "imputer",
                    SimpleImputer(strategy="most_frequent", keep_empty_features=True),
                ),
                (
                    "onehot",
                    OneHotEncoder(
                        handle_unknown="ignore",
                        min_frequency=25,
                        sparse_output=True,
                    ),
                ),
            ]
        )
        transformers.append(("categorical", category_pipeline, categorical_features))
    transformer = ColumnTransformer(transformers, remainder="drop")
    return Pipeline(
        [
            ("preprocessor", transformer),
            ("model", estimator),
        ]
    )


def _best_validation_metrics_by_model(
    candidates: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        kind = candidate["kind"]
        current = best.get(kind)
        if current is None or (
            candidate["validation_metrics"]["mae_brl"]
            < current["validation_metrics"]["mae_brl"]
        ):
            best[kind] = {
                "candidate": candidate["name"],
                "parameters": candidate["parameters"],
                "validation_metrics": candidate["validation_metrics"],
                "candidate_count": (
                    1 if current is None else current["candidate_count"] + 1
                ),
            }
        else:
            current["candidate_count"] += 1
    return best


def _fit_and_evaluate(
    records: list[dict[str, Any]],
    all_rows: list[dict[str, str]],
    output_dir: Path,
    workbook_output: Path,
    input_path: Path,
    random_state: int = RANDOM_STATE,
) -> dict[str, Any]:
    try:
        import numpy as np
        import pandas as pd
        import sklearn
        from sklearn.base import clone
    except ImportError as error:
        raise RuntimeError(
            "Dependências do AVM ausentes. Instale com "
            "`python -m pip install -r requirements-avm.txt`."
        ) from error
    try:
        import catboost
        from catboost import CatBoostRegressor

        catboost_version = catboost.__version__
    except ImportError as error:
        raise RuntimeError(
            "CatBoost não está instalado ou não é compatível com este Python. "
            "Instale com `python -m pip install -r requirements-avm.txt`."
        ) from error
    try:
        import xgboost
        from xgboost import XGBRegressor

        xgboost_version = xgboost.__version__
    except ImportError as error:
        raise RuntimeError(
            "XGBoost não está instalado ou não é compatível com este Python. "
            "Instale com `python -m pip install -r requirements-avm.txt`."
        ) from error

    numeric_features, categorical_features = select_feature_columns(records)
    feature_names = numeric_features + categorical_features
    partitions = _grouped_split(records, random_state)
    train_records = partitions["train"]
    validation_records = partitions["validation"]
    test_records = partitions["independent_geographic_test"]
    x_train = _frame(train_records, feature_names)
    x_validation = _frame(validation_records, feature_names)
    x_test = _frame(test_records, feature_names)
    y_train = np.asarray([record["target"] for record in train_records], dtype=float)
    y_validation = np.asarray(
        [record["target"] for record in validation_records], dtype=float
    )
    y_test = [record["target"] for record in test_records]
    log_y_train = np.log1p(y_train)
    log_y_validation = np.log1p(y_validation)

    candidates: list[dict[str, Any]] = []
    if CatBoostRegressor is not None:
        catboost_candidates = [
            {"depth": depth, "learning_rate": 0.05, "iterations": 500}
            for depth in (4, 6, 8)
        ]
        for parameters in catboost_candidates:
            estimator = CatBoostRegressor(
                **parameters,
                loss_function="RMSE",
                eval_metric="MAE",
                random_seed=random_state,
                verbose=False,
                allow_writing_files=False,
                thread_count=-1,
            )
            estimator.fit(
                x_train,
                log_y_train,
                cat_features=categorical_features,
                eval_set=(x_validation, log_y_validation),
                early_stopping_rounds=60,
                verbose=False,
            )
            validation_prediction = np.maximum(
                0, np.expm1(estimator.predict(x_validation))
            )
            candidates.append(
                {
                    "name": f"catboost_depth_{parameters['depth']}",
                    "kind": "catboost",
                    "parameters": parameters,
                    "validation_metrics": calculate_metrics(
                        y_validation.tolist(), validation_prediction.tolist()
                    ),
                    "estimator": estimator,
                }
            )

    if XGBRegressor is not None:
        xgboost_candidates = [
            {
                "max_depth": depth,
                "n_estimators": 500,
                "learning_rate": 0.05,
                "subsample": 0.8,
                "colsample_bytree": 0.8,
                "reg_lambda": 1.0,
            }
            for depth in (4, 6, 8)
        ]
        for parameters in xgboost_candidates:
            estimator = _make_sklearn_pipeline(
                numeric_features,
                categorical_features,
                XGBRegressor(
                    **parameters,
                    objective="reg:squarederror",
                    eval_metric="mae",
                    random_state=random_state,
                    n_jobs=-1,
                    tree_method="hist",
                    verbosity=0,
                ),
            )
            estimator.fit(x_train, log_y_train)
            validation_prediction = np.maximum(
                0, np.expm1(estimator.predict(x_validation))
            )
            candidates.append(
                {
                    "name": f"xgboost_depth_{parameters['max_depth']}",
                    "kind": "xgboost",
                    "parameters": parameters,
                    "validation_metrics": calculate_metrics(
                        y_validation.tolist(), validation_prediction.tolist()
                    ),
                    "estimator": estimator,
                }
            )

    forest = _make_random_forest(numeric_features, categorical_features)
    forest.fit(x_train, log_y_train)
    forest_validation_prediction = np.maximum(
        0, np.expm1(forest.predict(x_validation))
    )
    candidates.append(
        {
            "name": "random_forest",
            "kind": "random_forest",
            "parameters": {
                "n_estimators": 300,
                "max_features": 0.8,
                "min_samples_leaf": 3,
            },
            "validation_metrics": calculate_metrics(
                y_validation.tolist(), forest_validation_prediction.tolist()
            ),
            "estimator": forest,
        }
    )

    baseline_prediction = np.full(
        len(y_validation), float(np.median(y_train)), dtype=float
    )
    baseline_validation_metrics = calculate_metrics(
        y_validation.tolist(), baseline_prediction.tolist()
    )
    best_candidates = {
        kind: min(
            (candidate for candidate in candidates if candidate["kind"] == kind),
            key=lambda candidate: candidate["validation_metrics"]["mae_brl"],
        )
        for kind in {candidate["kind"] for candidate in candidates}
    }
    chosen = min(
        best_candidates.values(),
        key=lambda candidate: candidate["validation_metrics"]["mae_brl"],
    )
    development_records = train_records + validation_records
    x_development = _frame(development_records, feature_names)
    log_y_development = np.log1p(
        np.asarray([record["target"] for record in development_records], dtype=float)
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    workbook_output.parent.mkdir(parents=True, exist_ok=True)
    trained_models: dict[str, dict[str, Any]] = {}
    available_models: dict[str, dict[str, Any]] = {}
    for kind, candidate in best_candidates.items():
        if kind == "catboost":
            model = CatBoostRegressor(
                **candidate["parameters"],
                loss_function="RMSE",
                eval_metric="MAE",
                random_seed=random_state,
                verbose=False,
                allow_writing_files=False,
                thread_count=-1,
            )
            model.fit(
                x_development,
                log_y_development,
                cat_features=categorical_features,
                verbose=False,
            )
            model_path = output_dir / "offer_avm_catboost.cbm"
            model.save_model(str(model_path))
            importance_values = model.get_feature_importance()
            importance = {
                feature: float(value)
                for feature, value in zip(feature_names, importance_values)
            }
        else:
            model = clone(candidate["estimator"])
            model.fit(x_development, log_y_development)
            model_path = output_dir / (
                "offer_avm_xgboost.joblib"
                if kind == "xgboost"
                else "offer_avm.joblib"
            )
            import joblib

            joblib.dump(model, model_path)
            encoded_names = model.named_steps["preprocessor"].get_feature_names_out()
            encoded_importances = model.named_steps["model"].feature_importances_
            importance = {feature: 0.0 for feature in feature_names}
            for encoded, value in zip(encoded_names, encoded_importances):
                encoded_name = str(encoded).split("__", 1)[-1]
                source_feature = next(
                    (
                        feature
                        for feature in sorted(feature_names, key=len, reverse=True)
                        if encoded_name == feature
                        or encoded_name.startswith(feature + "_")
                    ),
                    encoded_name,
                )
                importance[source_feature] = (
                    importance.get(source_feature, 0.0) + float(value)
                )

        test_prediction = np.maximum(0, np.expm1(model.predict(x_test)))
        test_metrics = calculate_metrics(y_test, test_prediction.tolist())
        sorted_importance = dict(
            sorted(importance.items(), key=lambda item: item[1], reverse=True)
        )
        trained_models[kind] = {
            "model": model,
            "test_prediction": test_prediction,
            "test_metrics": test_metrics,
            "feature_importance": sorted_importance,
            "model_file": _report_path(model_path),
        }
        available_models[kind] = {
            "status": "trained",
            "candidate": candidate["name"],
            "parameters": candidate["parameters"],
            "validation_metrics": candidate["validation_metrics"],
            "independent_geographic_test_metrics": test_metrics,
            "feature_importance": sorted_importance,
            "model_file": _report_path(model_path),
        }
    selected = trained_models[chosen["kind"]]
    model = selected["model"]
    test_prediction = selected["test_prediction"]
    test_metrics = selected["test_metrics"]
    test_baseline_metrics = calculate_metrics(
        y_test,
        np.full(len(y_test), float(np.median(y_train)), dtype=float).tolist(),
    )

    inference_rows = [
        row for row in all_rows if _is_in_scope(row)
    ]
    output_features = _frame_from_rows(inference_rows, feature_names)
    output_predictions = np.maximum(0, np.expm1(model.predict(output_features)))
    test_source_rows = {record["source_row"] for record in test_records}
    development_source_rows = {
        record["source_row"] for record in development_records
    }
    predictions_by_row = {
        row.get("_source_excel_row", ""): float(prediction)
        for row, prediction in zip(inference_rows, output_predictions)
    }
    _write_prediction_workbook(
        input_path,
        workbook_output,
        predictions_by_row,
        test_source_rows,
        development_source_rows,
    )

    residual_path = output_dir / "test_residuals.csv"
    with residual_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "source_excel_row",
                "district",
                "target_brl",
                "prediction_brl",
                "residual_brl",
                "absolute_error_brl",
                "absolute_percentage_error",
            ),
        )
        writer.writeheader()
        for record, prediction in zip(test_records, test_prediction):
            error = float(prediction) - record["target"]
            writer.writerow(
                {
                    "source_excel_row": record["source_row"],
                    "district": record["district"],
                    "target_brl": round(record["target"], 2),
                    "prediction_brl": round(float(prediction), 2),
                    "residual_brl": round(error, 2),
                    "absolute_error_brl": round(abs(error), 2),
                    "absolute_percentage_error": round(
                        abs(error) / record["target"], 6
                    ),
                }
            )

    geography: dict[str, dict[str, Any]] = {}
    by_district: dict[str, list[tuple[float, float]]] = {}
    by_region: dict[str, list[tuple[float, float]]] = {}
    for record, prediction in zip(test_records, test_prediction):
        by_district.setdefault(record["district"], []).append(
            (record["target"], float(prediction))
        )
        by_region.setdefault(record["region"], []).append(
            (record["target"], float(prediction))
        )
    for district, pairs in sorted(by_district.items()):
        geography[district] = calculate_metrics(
            [pair[0] for pair in pairs], [pair[1] for pair in pairs]
        )
    region_metrics = {
        region: calculate_metrics(
            [pair[0] for pair in pairs], [pair[1] for pair in pairs]
        )
        for region, pairs in sorted(by_region.items())
    }

    candidates_summary = [
        {
            "name": candidate["name"],
            "kind": candidate["kind"],
            "parameters": candidate["parameters"],
            "validation_metrics": candidate["validation_metrics"],
        }
        for candidate in candidates
    ]
    catboost_status = "trained" if "catboost" in available_models else "not_trained"
    xgboost_status = "trained" if "xgboost" in available_models else "not_trained"
    model_status = {
        "random_forest": "trained" if "random_forest" in available_models else "not_trained",
        "catboost": catboost_status,
        "xgboost": xgboost_status,
    }
    report = {
        "status": "experimental_not_operationally_approved",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_file": input_path.name,
        "source_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
        "random_state": random_state,
        "runtime_versions": {
            "python": platform.python_version(),
            "catboost": catboost_version,
            "xgboost": xgboost_version,
            "pandas": pd.__version__,
            "scikit_learn": sklearn.__version__,
        },
        "model_status": model_status,
        "catboost_status": catboost_status,
        "xgboost_status": xgboost_status,
        "target_definition": (
            "0,90*OFERTA; 90% of asking price as a proxy, not a verified sale "
            "price or CAIXA appraisal"
        ),
        "discount_rate": 0.10,
        "region_discount_status": (
            "Uniform 10% target in source workbook; the Região column is empty, "
            "so region-specific rates were not inferred."
        ),
        "feature_columns": feature_names,
        "excluded_price_and_identifier_columns": list(EXCLUDED_PRICE_AND_ID_COLUMNS),
        "split_method": (
            "60/20/20 approximately by distinct Distrito groups; validation selected "
            "the model and parameters; independent geographic test was not used "
            "for selection"
        ),
        "official_region_validation": "available; independent_test_metrics_reported",
        "geographic_validation_by_region": region_metrics,
        "geographic_validation_by_district": geography,
        "partition_counts": {
            name: len(partition) for name, partition in partitions.items()
        },
        "inference_rows": len(inference_rows),
        "rows_outside_prediction_scope": len(all_rows) - len(inference_rows),
        "partition_district_counts": {
            name: len({record["district"] for record in partition})
            for name, partition in partitions.items()
        },
        "validation_candidates": candidates_summary,
        "validation_metrics_by_model": _best_validation_metrics_by_model(candidates),
        "available_models": available_models,
        "selected_model": chosen["name"],
        "selected_model_validation_metrics": chosen["validation_metrics"],
        "independent_geographic_test_metrics": test_metrics,
        "feature_importance": selected["feature_importance"],
        "outlier_analysis": _iqr_outlier_summary(records),
        "validation_median_baseline_metrics": baseline_validation_metrics,
        "independent_test_median_baseline_metrics": test_baseline_metrics,
        "model_file": selected["model_file"],
        "prediction_workbook": _report_path(workbook_output),
        "test_residuals_file": _report_path(residual_path),
        "limitations": [
            "O rótulo é um desconto fixo de 10% sobre oferta, não preço final de venda.",
            "A validação geográfica reserva distritos inteiros; os resultados também "
            "são reportados por Região.",
            "A data de captura dos anúncios não foi identificada; não há holdout temporal.",
            "O teste independente preserva distritos inteiros fora do treino e da seleção.",
            "Amostra de ofertas e alvo proxy não comprovam valor de mercado ou avaliação.",
        ],
    }
    importance_path = output_dir / "feature_importance.csv"
    with importance_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("feature", "importance"))
        writer.writeheader()
        for feature, value in sorted(
            importance.items(), key=lambda item: item[1], reverse=True
        ):
            writer.writerow({"feature": feature, "importance": value})
    return report


def _frame_from_rows(rows: list[dict[str, str]], feature_names: list[str]):
    import pandas as pd

    prepared = []
    for row in rows:
        features = build_feature_row(row)
        prepared.append({name: features[name] for name in feature_names})
    return pd.DataFrame(prepared, columns=feature_names)


def _write_prediction_workbook(
    input_path: Path,
    output_path: Path,
    predictions_by_row: dict[str, float],
    test_source_rows: set[str],
    development_source_rows: set[str],
) -> None:
    try:
        from openpyxl import load_workbook
    except ImportError as error:
        raise RuntimeError(
            "A exportação XLSX requer openpyxl; instale requirements-avm.txt."
        ) from error

    workbook = load_workbook(input_path)
    workbook.calculation.fullCalcOnLoad = True
    workbook.calculation.forceFullCalc = True
    workbook.calculation.calcMode = "auto"
    if SHEET_NAME not in workbook.sheetnames:
        raise ValueError(f"A aba obrigatória não existe: {SHEET_NAME}")
    worksheet = workbook[SHEET_NAME]
    headers = {
        str(cell.value).strip(): cell.column
        for cell in worksheet[1]
        if cell.value is not None
    }
    estimate_column = headers.get(OUTPUT_ESTIMATE_COLUMN, worksheet.max_column + 1)
    status_column = headers.get(
        OUTPUT_STATUS_COLUMN,
        estimate_column + 1
        if estimate_column > worksheet.max_column
        else worksheet.max_column + 1,
    )
    worksheet.cell(1, estimate_column, OUTPUT_ESTIMATE_COLUMN)
    worksheet.cell(1, status_column, OUTPUT_STATUS_COLUMN)

    source_rows = {
        row.get("_source_excel_row", ""): row
        for row in iter_xlsx_rows(input_path, SHEET_NAME, include_source_row=True)
    }
    for source_row, raw in source_rows.items():
        excel_row = int(source_row)
        if not _is_in_scope(raw):
            worksheet.cell(excel_row, estimate_column, None)
            worksheet.cell(excel_row, status_column, "fora_do_escopo")
            continue
        prediction = predictions_by_row.get(source_row)
        if prediction is None:
            worksheet.cell(excel_row, estimate_column, None)
            worksheet.cell(excel_row, status_column, "sem_estimativa")
            continue
        worksheet.cell(excel_row, estimate_column, round(prediction, 2)).number_format = (
            '"R$" #,##0.00'
        )
        if source_row in test_source_rows:
            status = "teste_geografico_independente"
        elif source_row in development_source_rows:
            status = "ajuste_in_sample"
        else:
            status = "sem_rotulo_estimado"
        worksheet.cell(excel_row, status_column, status)
    workbook.save(output_path)


def run(
    input_path: Path = DEFAULT_INPUT,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    workbook_output: Path = DEFAULT_WORKBOOK_OUTPUT,
    random_state: int = RANDOM_STATE,
) -> dict[str, Any]:
    if not input_path.is_file():
        raise FileNotFoundError(f"Planilha de entrada não encontrada: {input_path}")
    rows = list(iter_xlsx_rows(input_path, SHEET_NAME, include_source_row=True))
    if not rows:
        raise ValueError(f"A aba {SHEET_NAME} não possui registros.")
    required = {TARGET_COLUMN, OFFER_COLUMN, AGE_COLUMN, PRIVATE_AREA_COLUMN, DISTRICT_COLUMN}
    missing = required - set(rows[0])
    if missing:
        raise ValueError(f"Colunas obrigatórias ausentes: {sorted(missing)}")
    records, audit = prepare_training_records(rows)
    if len(records) < 100:
        raise ValueError(
            "Menos de 100 registros passaram pelos filtros; treinamento bloqueado."
        )
    result = _fit_and_evaluate(
        records, rows, output_dir, workbook_output, input_path, random_state
    )
    result["data_audit"] = audit
    report_path = output_dir / "avm_report.json"
    report_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--workbook-output", type=Path, default=DEFAULT_WORKBOOK_OUTPUT)
    args = parser.parse_args()
    try:
        report = run(args.input, args.output_dir, args.workbook_output)
    except (FileNotFoundError, ValueError, RuntimeError) as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
