"""Compare exploratory prediction corrections with leave-one-out validation."""
from __future__ import annotations

import argparse
import csv
import re
import unicodedata
from pathlib import Path
from statistics import median
from typing import Callable

import numpy as np
from openpyxl import load_workbook


def norm(value: object) -> str:
    value = unicodedata.normalize("NFD", str(value or ""))
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def metrics(actual: list[float], predicted: list[float]) -> dict[str, float | int]:
    errors = [p - y for y, p in zip(actual, predicted)]
    abs_errors = [abs(e) for e in errors]
    ape = [abs(e) / y * 100 for e, y in zip(errors, actual) if y > 0]
    return {
        "n": len(actual),
        "MAE_R$": sum(abs_errors) / len(abs_errors),
        "MAPE_%": sum(ape) / len(ape),
        "MdAPE_%": median(ape),
        "RMSE_R$": float(np.sqrt(np.mean(np.square(errors)))),
        "Bias_R$": sum(errors) / len(errors),
        "acima": sum(e > 0 for e in errors),
        "abaixo": sum(e < 0 for e in errors),
    }


def loocv(actual: np.ndarray, features: np.ndarray, fit_predict: Callable) -> list[float]:
    estimates = []
    for holdout in range(len(actual)):
        train = np.arange(len(actual)) != holdout
        estimates.append(float(fit_predict(actual[train], features[train], features[holdout])))
    return estimates


def fit_factor(y: np.ndarray, x: np.ndarray, test: float) -> float:
    denom = float(np.dot(x, x))
    factor = float(np.dot(x, y) / denom) if denom else 0.0
    return max(0.0, factor * test)


def fit_median_ratio(y: np.ndarray, x: np.ndarray, test: float) -> float:
    ratios = [target / pred for target, pred in zip(y, x) if pred > 0]
    return max(0.0, median(ratios) * test) if ratios else 0.0


def fit_affine(y: np.ndarray, x: np.ndarray, test: float) -> float:
    design = np.column_stack([np.ones(len(x)), x])
    coef, *_ = np.linalg.lstsq(design, y, rcond=None)
    return max(0.0, float(coef[0] + coef[1] * test))


def fit_area_median_rate(y: np.ndarray, areas: np.ndarray, test_area: float) -> float:
    rates = [target / area for target, area in zip(y, areas) if area > 0]
    return max(0.0, median(rates) * test_area) if rates else 0.0


def fit_area_linear(y: np.ndarray, areas: np.ndarray, test_area: float) -> float:
    design = np.column_stack([np.ones(len(areas)), areas])
    coef, *_ = np.linalg.lstsq(design, y, rcond=None)
    return max(0.0, float(coef[0] + coef[1] * test_area))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("dados/derivados"))
    args = parser.parse_args()
    book = load_workbook(args.input, read_only=True, data_only=True)
    sheet = book[book.sheetnames[0]]
    header_row = next(
        row for row in range(1, min(sheet.max_row, 20) + 1)
        if any(norm(sheet.cell(row, col).value) == "avaliacao" for col in range(1, sheet.max_column + 1))
    )
    headers = {norm(sheet.cell(header_row, col).value): col for col in range(1, sheet.max_column + 1) if sheet.cell(header_row, col).value is not None}
    actual_col = headers["avaliacao"]
    area_col = headers.get("area_priv") or headers.get("area_privativa")
    api_col = next((col for name, col in headers.items() if "guilherme" in name), None)
    if not area_col or not api_col:
        raise ValueError("A planilha precisa conter AREA PRIV. e a coluna com o resultado da API (Guilherme).")
    peer_cols = {sheet.cell(header_row, col).value: col for col in range(22, sheet.max_column + 1) if col != api_col and sheet.cell(header_row, col).value}
    rows = [row for row in range(header_row + 1, sheet.max_row + 1) if isinstance(sheet.cell(row, actual_col).value, (int, float)) and isinstance(sheet.cell(row, api_col).value, (int, float)) and isinstance(sheet.cell(row, area_col).value, (int, float))]
    y = np.array([float(sheet.cell(row, actual_col).value) for row in rows])
    raw = np.array([float(sheet.cell(row, api_col).value) for row in rows])
    areas = np.array([float(sheet.cell(row, area_col).value) for row in rows])

    methods: dict[str, list[float]] = {
        "API XGBoost anterior (sem ajuste)": raw.tolist(),
        "Fator proporcional (LOOCV)": loocv(y, raw, fit_factor),
        "Razão mediana (LOOCV)": loocv(y, raw, fit_median_ratio),
        "Correção linear intercepto + inclinação (LOOCV)": loocv(y, raw, fit_affine),
        "Área × mediana de R$/m² (LOOCV)": loocv(y, areas, fit_area_median_rate),
        "Regressão linear simples pela área (LOOCV)": loocv(y, areas, fit_area_linear),
    }
    for label, col in peer_cols.items():
        values = [sheet.cell(row, col).value for row in rows]
        if all(isinstance(value, (int, float)) for value in values):
            methods[f"Referência colega: {label}"] = [float(value) for value in values]

    source_stem = args.input.stem.removesuffix("_comp")
    catboost_path = args.output_dir / f"{source_stem}_catboost_resultado_avm.xlsx"
    if catboost_path.is_file():
        catboost_sheet = load_workbook(catboost_path, read_only=True, data_only=True).active
        catboost_header = next(
            row for row in range(1, min(catboost_sheet.max_row, 20) + 1)
            if any(norm(catboost_sheet.cell(row, col).value) == "valor_estimado_r" for col in range(1, catboost_sheet.max_column + 1))
        )
        catboost_col = next(
            col for col in range(1, catboost_sheet.max_column + 1)
            if norm(catboost_sheet.cell(catboost_header, col).value) == "valor_estimado_r"
        )
        methods["API CatBoost novo padrao (inferencias; alvo proxy)"] = [
            float(catboost_sheet.cell(row, catboost_col).value) for row in rows
        ]

    scores = {name: metrics(y.tolist(), values) for name, values in methods.items()}
    order = sorted(scores, key=lambda name: (scores[name]["MAPE_%"], scores[name]["MAE_R$"]))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = args.input.stem
    csv_path = args.output_dir / f"{stem}_metodos_loo.csv"
    report_path = args.output_dir / f"{stem}_avaliacao_metodos.md"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["imovel_linha", "avaliacao_referencia_brl", "area_privativa_m2", *methods])
        for idx, row in enumerate(rows):
            writer.writerow([row, y[idx], areas[idx], *[methods[name][idx] for name in methods]])

    report = [
        f"# Avaliação exploratória de métodos — {args.input.name}",
        "",
        f"Casos usados: {len(rows)}. Referência: coluna AVALIAÇÃO. Área: coluna AREA PRIV. A coluna Guilherme registra o XGBoost anterior; a saída CatBoost da API, agora padrão, é lida do arquivo {catboost_path.name} quando disponível.",
        "As correções próprias foram pontuadas por leave-one-out: para cada linha, os parâmetros foram ajustados nos outros casos e avaliados somente na linha separada.",
        "As previsões dos colegas são referências do mesmo conjunto de 28 casos, não validação independente nem comparação cega de protocolos.",
        "",
        "| Método | N | MAE (R$) | MAPE | MdAPE | RMSE (R$) | Viés (R$) | Acima | Abaixo |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in order:
        m = scores[name]
        report.append(f"| {name} | {m['n']} | {m['MAE_R$']:,.0f} | {m['MAPE_%']:.2f}% | {m['MdAPE_%']:.2f}% | {m['RMSE_R$']:,.0f} | {m['Bias_R$']:+,.0f} | {m['acima']} | {m['abaixo']} |")
    report += [
        "",
        "## Limites",
        "",
        "Esta amostra é pequena (28 apartamentos) e serve para triagem. A correção recalibrada não foi incorporada à API nem deve ser tratada como modelo aprovado. Um bom resultado aqui precisa ser confirmado em imóveis independentes, idealmente em outro período e região.",
        "A coluna AVALIAÇÃO foi tratada como valor de referência conforme o arquivo recebido. Se representar outro conceito, a avaliação precisa ser refeita com o alvo apropriado.",
    ]
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"Casos avaliados: {len(rows)}")
    for name in order:
        m = scores[name]
        print(f"{name}: MAPE {m['MAPE_%']:.2f}%, MAE R$ {m['MAE_R$']:,.0f}, viés R$ {m['Bias_R$']:+,.0f}")
    print(f"CSV por imóvel: {csv_path.resolve()}")
    print(f"Relatório: {report_path.resolve()}")


if __name__ == "__main__":
    main()
