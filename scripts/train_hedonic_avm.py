"""Train a transparent hedonic ridge challenger for the offer-price proxy."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__:
    from .train_offer_avm import (
        BASE_DIR,
        DEFAULT_INPUT,
        DISTRICT_COLUMN,
        REGION_COLUMN,
        SHEET_NAME,
        TARGET_COLUMN,
        OFFER_COLUMN,
        NUMERIC_FEATURES,
        CATEGORICAL_FEATURES,
        _report_path,
        _frame,
        _grouped_split,
        calculate_metrics,
        iter_xlsx_rows,
        prepare_training_records,
    )
else:
    from train_offer_avm import (
        BASE_DIR,
        DEFAULT_INPUT,
        DISTRICT_COLUMN,
        REGION_COLUMN,
        SHEET_NAME,
        TARGET_COLUMN,
        OFFER_COLUMN,
        NUMERIC_FEATURES,
        CATEGORICAL_FEATURES,
        _report_path,
        _frame,
        _grouped_split,
        calculate_metrics,
        iter_xlsx_rows,
        prepare_training_records,
    )


DEFAULT_OUTPUT_DIR = BASE_DIR / "models" / "hedonic_avm"
RANDOM_STATE = 42
RIDGE_ALPHAS = (0.1, 1.0, 10.0, 100.0)
SYSTEM2_NUMERIC_FEATURES = {"AREA PRIV.", "IDADE", "QUARTOS", "BANHEIROS", "VAGAS", "ELEVADOR"}
SYSTEM2_CATEGORICAL_FEATURES = {"Distrito", "CEP"}


def _split_calibration(train: list[dict[str, Any]], random_state: int):
    import numpy as np
    districts_by_region: dict[str, set[str]] = {}
    for record in train:
        districts_by_region.setdefault(record["region"], set()).add(record["district"])
    if any(len(districts) < 2 for districts in districts_by_region.values()):
        raise RuntimeError("Each region needs at least two train districts for geographic calibration.")
    rng = np.random.default_rng(random_state)
    selected = {
        str(rng.choice(sorted(districts)))
        for districts in districts_by_region.values()
    }
    calibration_records = [record for record in train if record["district"] in selected]
    fit_records = [record for record in train if record["district"] not in selected]
    if {r["district"] for r in fit_records} & {r["district"] for r in calibration_records}:
        raise RuntimeError("Geographic leakage between fit and offer-calibration partitions.")
    all_regions = set(districts_by_region)
    for part in (fit_records, calibration_records):
        if {r["region"] for r in part} != all_regions:
            raise RuntimeError("A fit/calibration partition does not cover all regions.")
    return fit_records, calibration_records


def _make_pipeline(numeric: list[str], categorical: list[str], alpha: float):
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, SplineTransformer, StandardScaler

    transformations = []
    if numeric:
        numeric_pipeline = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
                (
                    "splines",
                    SplineTransformer(
                        n_knots=4,
                        degree=2,
                        knots="quantile",
                        extrapolation="linear",
                        include_bias=False,
                    ),
                ),
                ("scale", StandardScaler()),
            ]
        )
        transformations.append(("numeric_splines", numeric_pipeline, numeric))
    if categorical:
        categorical_pipeline = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="most_frequent", keep_empty_features=True)),
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
        transformations.append(("categorical", categorical_pipeline, categorical))
    preprocessing = ColumnTransformer(transformations, remainder="drop")
    return Pipeline(
        [("features", preprocessing), ("ridge", Ridge(alpha=alpha, solver="lsqr"))]
    )


def _fit_log_model(records: list[dict[str, Any]], numeric: list[str], categorical: list[str], alpha: float):
    import numpy as np

    model = _make_pipeline(numeric, categorical, alpha)
    features = _frame(records, numeric + categorical)
    target_log = np.log(np.asarray([record["target"] for record in records], dtype=float))
    model.fit(features, target_log)
    residuals = target_log - model.predict(features)
    smearing = float(np.mean(np.exp(np.clip(residuals, -30.0, 30.0))))
    if not math.isfinite(smearing) or smearing <= 0:
        raise ValueError("Invalid log-scale retransformation factor.")
    return model, smearing


def _predict(model: Any, smearing: float, records: list[dict[str, Any]], feature_names: list[str]) -> list[float]:
    import numpy as np

    log_values = model.predict(_frame(records, feature_names))
    return np.exp(np.clip(log_values, -30.0, 30.0)) * smearing


def run(input_path: Path = DEFAULT_INPUT, output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    import joblib
    import sklearn
    from joblib import dump

    if not input_path.is_file():
        raise FileNotFoundError(f"Planilha de entrada não encontrada: {input_path}")
    rows = list(iter_xlsx_rows(input_path, SHEET_NAME, include_source_row=True))
    records, data_audit = prepare_training_records(rows)
    # The shared eligibility audit verifies that the source's 0.90*OFERTA
    # target matches the listed offer. System 2 v3 learns the full offer.
    records = [{**record, "target": float(record["target"]) / 0.9} for record in records]
    if len(records) < 100:
        raise ValueError("Menos de 100 registros elegíveis; treinamento challenger bloqueado.")

    records = [{
        **record,
        "target": float(record["target"]),
        "features": {**record["features"], "CEP": "".join(ch for ch in str(record["features"].get("CEP") or "") if ch.isdigit())[:5] or "desconhecido"},
    } for record in records]
    numeric = [
        name for name in NUMERIC_FEATURES
        if name in SYSTEM2_NUMERIC_FEATURES
        and any(record["features"][name] is not None for record in records)
    ]
    categorical = [
        name for name in CATEGORICAL_FEATURES
        if name in SYSTEM2_CATEGORICAL_FEATURES
        and len({record["features"][name] for record in records}) > 1
    ]
    if not numeric or not categorical:
        raise ValueError("O conjunto distinto de atributos do Sistema 2 não está disponível.")
    feature_names = numeric + categorical
    partitions = _grouped_split(records, RANDOM_STATE)
    train, calibration = _split_calibration(partitions["train"], RANDOM_STATE + 2)
    partitions["model_fit"] = train
    partitions["offer_calibration"] = calibration
    del partitions["train"]
    validation = partitions["validation"]
    development = train + validation
    test = partitions["independent_geographic_test"]

    alpha_results = []
    for alpha in RIDGE_ALPHAS:
        model, smear = _fit_log_model(train, numeric, categorical, alpha)
        predicted = _predict(model, smear, validation, feature_names)
        actual = [float(record["target"]) for record in validation]
        alpha_results.append({
            "alpha": alpha,
            "validation_metrics": calculate_metrics(actual, predicted),
        })
    selected = min(alpha_results, key=lambda result: result["validation_metrics"]["mae_brl"])
    final_model, final_smearing = _fit_log_model(
        development, numeric, categorical, float(selected["alpha"])
    )
    calibration_raw = _predict(final_model, final_smearing, calibration, feature_names)
    calibration_actual = [float(record["target"]) for record in calibration]
    calibration_factor = float(statistics.median(
        actual / prediction for actual, prediction in zip(calibration_actual, calibration_raw)
        if prediction > 0
    ))
    if not math.isfinite(calibration_factor) or calibration_factor <= 0:
        raise ValueError("Offer calibration factor must be finite and positive.")
    calibration_adjusted = [prediction * calibration_factor for prediction in calibration_raw]
    test_predictions_raw = _predict(final_model, final_smearing, test, feature_names)
    test_predictions = [prediction * calibration_factor for prediction in test_predictions_raw]
    test_actual = [float(record["target"]) for record in test]
    metrics = calculate_metrics(test_actual, test_predictions)
    median_baseline = [float(sorted(record["target"] for record in development)[len(development) // 2])] * len(test)
    baseline_metrics = calculate_metrics(test_actual, median_baseline)

    report: dict[str, Any] = {
        "model_id": "hedonic_spline_ridge_v4_offer_calibrated",
        "status": "experimental_challenger_not_approved_for_operational_use",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "runtime_versions": {
            "python": platform.python_version(),
            "scikit_learn": sklearn.__version__,
            "joblib": joblib.__version__,
        },
        "input_file": _report_path(input_path),
        "input_sheet": SHEET_NAME,
        "target": OFFER_COLUMN,
        "target_definition": "100% of asking/list price reconstructed from the audited 0.90*OFERTA source target; not verified sale/appraisal",
        "method": {
            "family": "regularized hedonic regression",
            "feature_selection": "Ridge spline hedonic model with physical attributes, district, and five-digit CEP prefix; excludes System 1 income, census-sector, and IPTU-standard features.",
            "equation": "log(target) = intercept + additive quadratic spline terms for numeric features + one-hot categorical effects; prediction = exp(linear predictor) * Duan smearing factor",
            "numeric_features": numeric,
            "categorical_features": categorical,
            "spline_knots": 4,
            "spline_degree": 2,
            "ridge_alpha_selected_by_validation_mae": float(selected["alpha"]),
            "smearing_factor_fit_on_development_partition": final_smearing,
        },
        "selection": alpha_results,
        "offer_calibration": {
            "method": "median observed_offer / raw_prediction on a separate geographically grouped calibration partition",
            "factor": calibration_factor,
            "n": len(calibration),
            "calibration_metrics_before_factor": calculate_metrics(calibration_actual, calibration_raw),
            "calibration_metrics_after_factor_not_independent": calculate_metrics(calibration_actual, calibration_adjusted),
        },
        "independent_geographic_test": metrics,
        "independent_geographic_test_before_offer_calibration": calculate_metrics(test_actual, test_predictions_raw),
        "independent_geographic_test_median_baseline": baseline_metrics,
        "partition_counts": {name: len(part) for name, part in partitions.items()},
        "partition_district_counts": {
            name: len({record["district"] for record in part})
            for name, part in partitions.items()
        },
        "target_leakage_check": {
            "target_column_used_as_feature": False,
            "offer_column_used_as_feature": False,
            "calibration_district_overlap_with_fit": False,
            "calibration_uses_peer_predictions": False,
            "district_group_overlap": False,
        },
        "data_audit": data_audit,
        "limitations": [
            "The model learns the asking/list price, reconstructed from the source workbook's audited 90%-of-offer target; it does not learn verified sale/appraisal values.",
            "The geographic split does not establish temporal performance or representativeness.",
            "This challenger is not an appraisal model and is not approved for operational or credit decisions.",
        ],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / "hedonic_spline_ridge_v4_offer_calibrated.joblib"
    dump(
        {
            "model_id": report["model_id"],
            "model": final_model,
            "smearing_factor": final_smearing,
            "offer_calibration_factor": calibration_factor,
            "feature_names": feature_names,
            "report": report,
        },
        model_path,
    )
    (output_dir / "hedonic_spline_ridge_v4_offer_calibrated.sha256").write_text(
        hashlib.sha256(model_path.read_bytes()).hexdigest() + "  " + model_path.name + "\n",
        encoding="ascii",
    )
    report["artifact"] = _report_path(model_path)
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    try:
        result = run(args.input, args.output_dir)
    except (FileNotFoundError, ValueError, RuntimeError) as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
