"""LOOCV experiment: learn appraisal values directly from TESTE_comp labels."""
from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path

import numpy as np
from openpyxl import load_workbook
from sklearn.ensemble import ExtraTreesRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import Ridge


def norm(value: object) -> str:
    value = unicodedata.normalize("NFD", str(value or ""))
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def metrics(actual: np.ndarray, predicted: np.ndarray) -> tuple[float, float, float, float]:
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
    parser.add_argument("proxy_predictions", type=Path)
    args = parser.parse_args()
    sheet = load_workbook(args.comparison, data_only=True, read_only=True).active
    proxy = load_workbook(args.proxy_predictions, data_only=True, read_only=True).active
    header = next(r for r in range(1, 20) if any(
        norm(sheet.cell(r, c).value) == "avaliacao" for c in range(1, sheet.max_column + 1)
    ))
    cols = {norm(sheet.cell(header, c).value): c for c in range(1, sheet.max_column + 1)}
    proxy_header = next(r for r in range(1, 20) if any(
        norm(proxy.cell(r, c).value) == "valor_estimado_r" for c in range(1, proxy.max_column + 1)
    ))
    proxy_col = next(c for c in range(1, proxy.max_column + 1)
                     if norm(proxy.cell(proxy_header, c).value) == "valor_estimado_r")
    rows = [r for r in range(header + 1, sheet.max_row + 1)
            if isinstance(sheet.cell(r, cols["avaliacao"]).value, (int, float))]
    actual = np.asarray([float(sheet.cell(r, cols["avaliacao"]).value) for r in rows])
    proxy_predictions = np.asarray([
        float(proxy.cell(proxy_header + 1 + i, proxy_col).value) for i in range(len(rows))
    ])
    numeric_cols = ["area_priv", "idade", "quartos", "banheiros", "vagas", "elevador", "area_total"]
    X_num = np.asarray([
        [float(sheet.cell(row, cols[name]).value)
         if isinstance(sheet.cell(row, cols[name]).value, (int, float)) else np.nan
         for name in numeric_cols]
        for row in rows
    ])
    districts = np.asarray([
        str(sheet.cell(row, cols["bairro_subdistrito"]).value or "desconhecido").strip().upper()
        for row in rows
    ], dtype=object)
    candidates: dict[str, list[float]] = {
        "CatBoost proxy atual": proxy_predictions.tolist(),
        "Random Forest direto (log avaliação)": [],
        "Extra Trees direto (log avaliação)": [],
        "Ridge direto (log avaliação)": [],
    }
    for heldout in range(len(actual)):
        train = np.arange(len(actual)) != heldout
        for name, estimator in [
            ("Random Forest direto (log avaliação)", RandomForestRegressor(
                n_estimators=400, min_samples_leaf=3, max_features=0.8, random_state=42, n_jobs=1)),
            ("Extra Trees direto (log avaliação)", ExtraTreesRegressor(
                n_estimators=400, min_samples_leaf=3, max_features=0.8, random_state=42, n_jobs=1)),
        ]:
            model = make_pipeline(SimpleImputer(strategy="median"), estimator)
            model.fit(X_num[train], np.log(actual[train]))
            candidates[name].append(float(np.exp(model.predict(X_num[heldout:heldout + 1])[0])))

        transformer = ColumnTransformer([
            ("numeric", make_pipeline(SimpleImputer(strategy="median"), StandardScaler()), list(range(X_num.shape[1]))),
            ("district", OneHotEncoder(handle_unknown="ignore"), [X_num.shape[1]]),
        ])
        X_mixed = np.column_stack((X_num, districts))
        model = make_pipeline(transformer, Ridge(alpha=10))
        model.fit(X_mixed[train], np.log(actual[train]))
        candidates["Ridge direto (log avaliação)"].append(
            float(np.exp(model.predict(X_mixed[heldout:heldout + 1])[0]))
        )

    ranked = sorted(candidates, key=lambda name: metrics(actual, np.asarray(candidates[name]))[0])
    print(f"Casos: {len(actual)}; cada estimativa foi ajustada nos outros {len(actual)-1} casos.")
    print("MAPE | MAE (R$) | viés (R$) | RMSE (R$) | método")
    for name in ranked:
        mape, mae, bias, rmse = metrics(actual, np.asarray(candidates[name]))
        print(f"{mape:5.2f}% | {mae:9,.0f} | {bias:+9,.0f} | {rmse:9,.0f} | {name}")


if __name__ == "__main__":
    main()
