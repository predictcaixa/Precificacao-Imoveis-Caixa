"""Nested leave-one-out evaluation of feature-based price calibration."""
from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path

import numpy as np
from openpyxl import load_workbook
from sklearn.impute import SimpleImputer
from sklearn.neighbors import KNeighborsRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge


def norm(value: object) -> str:
    value = unicodedata.normalize("NFD", str(value or ""))
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def score(actual: np.ndarray, predicted: np.ndarray) -> tuple[float, float, float, float]:
    error = predicted - actual
    return (
        float(np.mean(np.abs(error) / actual) * 100),
        float(np.mean(np.abs(error))),
        float(np.mean(error)),
        float(np.sqrt(np.mean(error**2))),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("comparison", type=Path)
    parser.add_argument("predictions", type=Path)
    args = parser.parse_args()
    sheet = load_workbook(args.comparison, data_only=True, read_only=True).active
    result = load_workbook(args.predictions, data_only=True, read_only=True).active
    header = next(r for r in range(1, 20) if any(
        norm(sheet.cell(r, c).value) == "avaliacao" for c in range(1, sheet.max_column + 1)
    ))
    cols = {norm(sheet.cell(header, c).value): c for c in range(1, sheet.max_column + 1)}
    result_header = next(r for r in range(1, 20) if any(
        norm(result.cell(r, c).value) == "valor_estimado_r" for c in range(1, result.max_column + 1)
    ))
    result_col = next(c for c in range(1, result.max_column + 1)
                      if norm(result.cell(result_header, c).value) == "valor_estimado_r")
    rows = [r for r in range(header + 1, sheet.max_row + 1)
            if isinstance(sheet.cell(r, cols["avaliacao"]).value, (int, float))]
    actual = np.asarray([float(sheet.cell(r, cols["avaliacao"]).value) for r in rows])
    raw = np.asarray([float(result.cell(result_header + 1 + i, result_col).value)
                      for i in range(len(rows))])
    # Features are available on the source worksheet; no peer outputs or labels are used as predictors.
    feature_names = ["area_priv", "idade", "quartos", "banheiros", "vagas", "elevador", "area_total"]
    x_values = []
    for row in rows:
        vals = []
        for name in feature_names:
            value = sheet.cell(row, cols[name]).value
            vals.append(float(value) if isinstance(value, (int, float)) else np.nan)
        x_values.append([np.log(raw[len(x_values)]), *vals])
    X = np.asarray(x_values, dtype=float)
    y = np.log(actual)

    settings = {
        "Ridge alpha": [("ridge", alpha) for alpha in (0.01, 0.1, 1, 10, 100)],
        "KNN k": [("knn", k) for k in (3, 5, 7, 9)],
    }
    predictions: dict[str, list[float]] = {name: [] for name in settings}
    for holdout in range(len(actual)):
        outer_train = np.arange(len(actual)) != holdout
        X_train, y_train = X[outer_train], y[outer_train]
        for method, choices in settings.items():
            best_choice, best_error = None, float("inf")
            for kind, parameter in choices:
                errors = []
                for inner_holdout in range(len(y_train)):
                    inner_train = np.arange(len(y_train)) != inner_holdout
                    estimator = (
                        Ridge(alpha=parameter) if kind == "ridge"
                        else KNeighborsRegressor(n_neighbors=min(parameter, int(inner_train.sum())), weights="distance")
                    )
                    model = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), estimator)
                    model.fit(X_train[inner_train], y_train[inner_train])
                    estimate = float(np.exp(model.predict(X_train[inner_holdout:inner_holdout + 1])[0]))
                    target = float(np.exp(y_train[inner_holdout]))
                    errors.append(abs(estimate - target) / target)
                mean_error = float(np.mean(errors))
                if mean_error < best_error:
                    best_error, best_choice = mean_error, (kind, parameter)
            kind, parameter = best_choice
            estimator = Ridge(alpha=parameter) if kind == "ridge" else KNeighborsRegressor(
                n_neighbors=min(parameter, len(y_train)), weights="distance"
            )
            model = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), estimator)
            model.fit(X_train, y_train)
            predictions[method].append(float(np.exp(model.predict(X[holdout:holdout + 1])[0])))

    print(f"Casos: {len(actual)}; ajuste interno e avaliação externa: leave-one-out aninhado.")
    print("MAPE | MAE (R$) | viés (R$) | RMSE (R$) | método")
    for name, values in [("CatBoost sem calibração", raw.tolist()), *predictions.items()]:
        mape, mae, bias, rmse = score(actual, np.asarray(values))
        print(f"{mape:5.2f}% | {mae:9,.0f} | {bias:+9,.0f} | {rmse:9,.0f} | {name}")


if __name__ == "__main__":
    main()
