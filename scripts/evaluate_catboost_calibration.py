"""Evaluate post-hoc price calibration on TESTE_comp using leave-one-out."""
from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path
from statistics import median

import numpy as np
from openpyxl import load_workbook
from sklearn.linear_model import HuberRegressor, Ridge


def norm(value: object) -> str:
    value = unicodedata.normalize("NFD", str(value or ""))
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def metric(actual: np.ndarray, predicted: np.ndarray) -> tuple[float, float, float, float]:
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

    comparison = load_workbook(args.comparison, data_only=True, read_only=True).active
    result = load_workbook(args.predictions, data_only=True, read_only=True).active
    comparison_header = next(
        row for row in range(1, min(20, comparison.max_row) + 1)
        if any(norm(comparison.cell(row, col).value) == "avaliacao"
               for col in range(1, comparison.max_column + 1))
    )
    actual_col = next(
        col for col in range(1, comparison.max_column + 1)
        if norm(comparison.cell(comparison_header, col).value) == "avaliacao"
    )
    result_header = next(
        row for row in range(1, min(20, result.max_row) + 1)
        if any(norm(result.cell(row, col).value) == "valor_estimado_r"
               for col in range(1, result.max_column + 1))
    )
    prediction_col = next(
        col for col in range(1, result.max_column + 1)
        if norm(result.cell(result_header, col).value) == "valor_estimado_r"
    )
    actual = np.asarray([
        float(comparison.cell(row, actual_col).value)
        for row in range(comparison_header + 1, comparison.max_row + 1)
        if isinstance(comparison.cell(row, actual_col).value, (int, float))
    ])
    raw = np.asarray([
        float(result.cell(row, prediction_col).value)
        for row in range(result_header + 1, result.max_row + 1)
        if isinstance(result.cell(row, prediction_col).value, (int, float))
    ])
    if len(actual) != len(raw) or not len(actual):
        raise ValueError(f"Linhas incompatíveis: referência={len(actual)}, previsões={len(raw)}")
    if np.any(actual <= 0) or np.any(raw <= 0):
        raise ValueError("Todos os valores de avaliação e previsão precisam ser positivos.")

    candidates: dict[str, list[float]] = {"CatBoost sem calibração": raw.tolist()}
    for name in ("Escala OLS", "Razão mediana", "Affine", "Log-log", "Log-log Ridge", "Log-log Huber"):
        candidates[name] = []
    for holdout in range(len(actual)):
        train = np.arange(len(actual)) != holdout
        y, x, test = actual[train], raw[train], raw[holdout]
        candidates["Escala OLS"].append(float(test * np.dot(x, y) / np.dot(x, x)))
        candidates["Razão mediana"].append(float(test * median(y / x)))
        coef = np.linalg.lstsq(np.column_stack((np.ones(len(x)), x)), y, rcond=None)[0]
        candidates["Affine"].append(max(0.0, float(coef[0] + coef[1] * test)))
        log_x, log_y = np.log(x).reshape(-1, 1), np.log(y)
        coef = np.linalg.lstsq(np.column_stack((np.ones(len(x)), log_x[:, 0])), log_y, rcond=None)[0]
        candidates["Log-log"].append(float(np.exp(coef[0] + coef[1] * np.log(test))))
        ridge = Ridge(alpha=10).fit(log_x, log_y)
        candidates["Log-log Ridge"].append(float(np.exp(ridge.predict([[np.log(test)]])[0])))
        huber = HuberRegressor(epsilon=1.35).fit(log_x, log_y)
        candidates["Log-log Huber"].append(float(np.exp(huber.predict([[np.log(test)]])[0])))

    ranked = sorted(candidates, key=lambda name: metric(actual, np.asarray(candidates[name]))[0])
    print(f"Casos comparados: {len(actual)}; validação: leave-one-out.")
    print("MAPE | MAE (R$) | viés (R$) | RMSE (R$) | método")
    for name in ranked:
        mape, mae, bias, rmse = metric(actual, np.asarray(candidates[name]))
        print(f"{mape:5.2f}% | {mae:9,.0f} | {bias:+9,.0f} | {rmse:9,.0f} | {name}")


if __name__ == "__main__":
    main()
