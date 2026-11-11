"""Evaluate CatBoost imitation of peer predictions with leave-one-out CV."""
from __future__ import annotations

import argparse
import math
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor
from openpyxl import load_workbook

from train_offer_avm import CATEGORICAL_FEATURES, FEATURE_ALLOWLIST


def norm(value: object) -> str:
    value = unicodedata.normalize("NFD", str(value or ""))
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path, nargs="?", default=Path("dados/derivados/TESTE_comp.xlsx"))
    parser.add_argument("--output", type=Path, default=Path("dados/derivados/TESTE_peer_catboost_loo.csv"))
    args = parser.parse_args()

    sheet = load_workbook(args.workbook, data_only=True, read_only=True).active
    header = next(r for r in range(1, 25) if any(norm(sheet.cell(r, c).value) == "avaliacao" for c in range(1, sheet.max_column + 1)))
    cols = {norm(sheet.cell(header, c).value): c for c in range(1, sheet.max_column + 1)}
    analysis_col = next((name for name in cols if name.startswith("analise_evolutiva_mediana_dos_modelos_empatados_no_teste")), None)
    required = ("avaliacao", "januario_catboost", analysis_col)
    missing = [name for name in required if name not in cols]
    if missing:
        raise ValueError(f"Colunas ausentes: {missing}; encontradas: {list(cols)}")

    rows = [r for r in range(header + 1, sheet.max_row + 1) if isinstance(sheet.cell(r, cols["avaliacao"]).value, (int, float))]
    names = {
        "LATITUDE": None, "LONGITUDE": None, "IDADE": "idade", "QUARTOS": "quartos",
        "BANHEIROS": "banheiros", "VAGAS": "vagas", "ELEVADOR": "elevador",
        "RENDA MEDIANA IBGE 2022 (R$)": None, "RENDA MÃ‰DIA IBGE 2022 (R$)": None,
        "Ãrea total": "area_total", "AREA PRIV.": "area_priv", "CEP": "cep",
        "RegiÃ£o": None, "Distrito": "bairro_subdistrito", "SETOR CENSITÃRIO 2022": None,
        "PadrÃ£o (IPTU)": None,
    }
    x_rows, records = [], []
    for row in rows:
        values = {}
        for feature, source in names.items():
            value = sheet.cell(row, cols[source]).value if source in cols else None
            if feature == "ELEVADOR":
                # In this workbook, 1 means unknown/not stated and 2 means confirmed.
                value = 1 if value == 2 else (0 if value == 0 else None)
            if feature in CATEGORICAL_FEATURES:
                value = str(value).strip() if value is not None else ""
                value = value or "desconhecido"
                if feature == "CEP":
                    value = value.replace("-", "")
            elif value is not None:
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    value = None
            values[feature] = value
        x_rows.append(values)
        records.append({
            "excel_row": row,
            "item": sheet.cell(row, cols.get("x", 1)).value,
            "actual": float(sheet.cell(row, cols["avaliacao"]).value),
            "januario": float(sheet.cell(row, cols[required[1]]).value),
            "analise": float(sheet.cell(row, cols[required[2]]).value),
        })

    X = pd.DataFrame(x_rows, columns=FEATURE_ALLOWLIST)
    for category in CATEGORICAL_FEATURES:
        X[category] = X[category].astype(object).where(X[category].notna(), "desconhecido").astype(str)
    y_peer = np.log(np.asarray([(x["januario"] + x["analise"]) / 2 for x in records]))
    y_jan = np.log(np.asarray([x["januario"] for x in records]))
    y_analise = np.log(np.asarray([x["analise"] for x in records]))
    y_actual = np.asarray([x["actual"] for x in records])

    def loo(target: np.ndarray, depth: int, iterations: int, l2: float) -> np.ndarray:
        preds = []
        for holdout in range(len(X)):
            train = np.arange(len(X)) != holdout
            model = CatBoostRegressor(
                iterations=iterations, depth=depth, learning_rate=0.03,
                loss_function="RMSE", l2_leaf_reg=l2, random_seed=42,
                verbose=False, allow_writing_files=False, thread_count=1,
            )
            model.fit(X.iloc[train], target[train], cat_features=list(CATEGORICAL_FEATURES))
            preds.append(math.exp(float(model.predict(X.iloc[[holdout]])[0])))
        return np.asarray(preds)

    def score(target: np.ndarray, pred: np.ndarray) -> tuple[float, float, float, float]:
        err = pred - target
        return (float(np.mean(np.abs(err) / target) * 100), float(np.mean(np.abs(err))), float(np.mean(err)), float(np.sqrt(np.mean(err**2))))

    candidates = {}
    for depth, iters, l2 in ((2, 60, 15),):
        name = f"CatBoost peer depth={depth}, iterations={iters}, L2={l2}"
        candidates[name] = loo(y_peer, depth, iters, l2)
    peer_mid = np.exp(y_peer)
    peer_mape = float(np.mean(np.abs(peer_mid - y_actual) / y_actual) * 100)
    peer_mae = float(np.mean(np.abs(peer_mid - y_actual)))
    print(f"N={len(rows)}; validação LOO; cada previsão de colega é alvo, nunca variável de entrada.")
    print(f"Peer médio contra AVALIAÇÃO: MAPE={peer_mape:.2f}%, MAE=R${peer_mae:,.0f}")
    print("Modelo | MAPE vs peer médio | MAE vs peer médio | MAPE vs AVALIAÇÃO | MAE vs AVALIAÇÃO")
    output = []
    for name, pred in candidates.items():
        peer_stats = score(peer_mid, pred)
        actual_stats = score(y_actual, pred)
        print(f"{name} | {peer_stats[0]:.2f}% | R${peer_stats[1]:,.0f} | {actual_stats[0]:.2f}% | R${actual_stats[1]:,.0f}")
        for rec, value in zip(records, pred):
            output.append({**rec, "peer_mean": (rec["januario"] + rec["analise"]) / 2, name: value})
    pd.DataFrame(output).to_csv(args.output, index=False, encoding="utf-8-sig")
    print(f"Previsões LOO gravadas em {args.output}")


if __name__ == "__main__":
    main()
