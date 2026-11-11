"""Create a labeled, color-coded workbook comparing AVM output with peer results."""

from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


def normalize(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def locate_header(sheet: Any, required: set[str], scan_rows: int = 30) -> int:
    for row in range(1, min(sheet.max_row, scan_rows) + 1):
        names = {normalize(sheet.cell(row, col).value) for col in range(1, sheet.max_column + 1)}
        if required <= names:
            return row
    raise ValueError(f"Cabeçalho não encontrado; campos necessários: {sorted(required)}")


def column_map(sheet: Any, header_row: int) -> dict[str, int]:
    return {
        normalize(sheet.cell(header_row, col).value): col
        for col in range(1, sheet.max_column + 1)
        if sheet.cell(header_row, col).value is not None
    }


def find_prediction_column(sheet: Any) -> tuple[int, int]:
    header = locate_header(sheet, {"valor_estimado_r"})
    columns = column_map(sheet, header)
    return header, columns["valor_estimado_r"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("comparison", type=Path, help="Workbook with appraisal, offer and peer predictions")
    parser.add_argument("predictions", type=Path, help="Workbook returned by the API pipeline")
    parser.add_argument("--output", type=Path, help="Output workbook; defaults to *_Guilherme_CatBoost_7pct.xlsx")
    parser.add_argument("--model-label", default="CatBoost", help="Name shown in the Guilherme prediction header")
    parser.add_argument("--tolerance-percent", type=float, default=7.0, help="Peer-match tolerance, default 7%%")
    args = parser.parse_args()
    if not 0 < args.tolerance_percent <= 100:
        raise ValueError("A tolerância deve estar entre 0 e 100 por cento.")

    comparison_path = args.comparison.resolve()
    prediction_path = args.predictions.resolve()
    output_path = args.output.resolve() if args.output else comparison_path.with_name(
        f"{comparison_path.stem}_Guilherme_{normalize(args.model_label)}_{args.tolerance_percent:g}pct.xlsx"
    )
    if comparison_path == output_path or prediction_path == output_path:
        raise ValueError("O arquivo de saída deve ser diferente dos arquivos de entrada.")

    workbook = load_workbook(comparison_path)
    sheet = workbook[workbook.sheetnames[0]]
    header = locate_header(sheet, {"avaliacao", "oferta"})
    columns = column_map(sheet, header)
    appraisal_col, offer_col = columns["avaliacao"], columns["oferta"]
    item_col = columns.get("x")

    prediction_sheet = load_workbook(prediction_path, data_only=True, read_only=True).active
    prediction_header, prediction_col = find_prediction_column(prediction_sheet)
    prediction_columns = column_map(prediction_sheet, prediction_header)
    prediction_item_col = prediction_columns.get("x")
    prediction_by_item: dict[str, float] = {}
    ordered_predictions: list[float] = []
    for row in range(prediction_header + 1, prediction_sheet.max_row + 1):
        value = prediction_sheet.cell(row, prediction_col).value
        if not isinstance(value, (int, float)) or value <= 0:
            continue
        ordered_predictions.append(float(value))
        if prediction_item_col:
            key = str(prediction_sheet.cell(row, prediction_item_col).value).strip()
            if key:
                prediction_by_item[key] = float(value)

    # Peer prediction columns are numeric model/team columns to the right of OFFER,
    # excluding appraisal, offer, IDs and any previous Guilherme output.
    peer_columns = []
    for col in range(offer_col + 1, sheet.max_column + 1):
        title = normalize(sheet.cell(header, col).value)
        if not title or title.startswith("guilherme") or title in {"x", "avaliacao", "oferta"}:
            continue
        if any(isinstance(sheet.cell(row, col).value, (int, float)) for row in range(header + 1, sheet.max_row + 1)):
            peer_columns.append(col)
    if not peer_columns:
        raise ValueError("Não encontrei colunas numéricas com previsões de outros colegas.")

    # Replace an existing Guilherme output column, or append one if absent.
    output_col = next(
        (col for col in range(1, sheet.max_column + 1) if normalize(sheet.cell(header, col).value).startswith("guilherme")),
        sheet.max_column + 1,
    )
    direct_col = sheet.max_column + 1 if output_col <= sheet.max_column else output_col + 1
    match_col = direct_col + 1
    tolerance = args.tolerance_percent / 100
    sheet.cell(header, appraisal_col).value = "AVALIAÇÃO | referência recebida (não calculada pelo modelo)"
    sheet.cell(header, offer_col).value = "OFERTA | valor anunciado de referência"
    sheet.cell(header, output_col).value = (
        f"Guilherme | {args.model_label} — estimativa experimental do alvo proxy 90% × OFERTA"
    )
    sheet.cell(header, direct_col).value = "Guilherme | cálculo direto 90% × OFERTA (fórmula, não CatBoost)"
    sheet.cell(header, match_col).value = (
        f"Guilherme | colegas dentro de ±{args.tolerance_percent:g}% da previsão"
    )

    dark_blue = PatternFill("solid", fgColor="1F4E78")
    green = PatternFill("solid", fgColor="C6EFCE")
    yellow = PatternFill("solid", fgColor="FFEB9C")
    for col in range(appraisal_col, match_col + 1):
        cell = sheet.cell(header, col)
        cell.fill = dark_blue
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(wrap_text=True, vertical="center")

    row_count = matched_rows = matched_peer_pairs = 0
    for row in range(header + 1, sheet.max_row + 1):
        if item_col and prediction_item_col:
            item = str(sheet.cell(row, item_col).value).strip()
            prediction = prediction_by_item.get(item)
        else:
            prediction = ordered_predictions[row - header - 1] if row - header - 1 < len(ordered_predictions) else None
        if not isinstance(prediction, (int, float)) or prediction <= 0:
            continue

        estimate_cell = sheet.cell(row, output_col, float(prediction))
        estimate_cell.number_format = 'R$ #,##0.00'
        offer = sheet.cell(row, offer_col).value
        direct_cell = sheet.cell(row, direct_col)
        direct_cell.value = round(float(offer) * 0.90, 2) if isinstance(offer, (int, float)) and offer > 0 else None
        direct_cell.number_format = 'R$ #,##0.00'

        matches = []
        peer_cells = []
        for col in peer_columns:
            peer_value = sheet.cell(row, col).value
            if isinstance(peer_value, (int, float)) and peer_value > 0 and abs(float(prediction) / float(peer_value) - 1) <= tolerance:
                matches.append(str(sheet.cell(header, col).value).strip())
                peer_cells.append(sheet.cell(row, col))
        status = sheet.cell(row, match_col)
        status.value = "; ".join(matches) if matches else f"Nenhum colega dentro de ±{args.tolerance_percent:g}%"
        status.fill = green if matches else yellow
        estimate_cell.fill = green if matches else yellow
        for cell in peer_cells:
            cell.fill = green
        row_count += 1
        matched_rows += bool(matches)
        matched_peer_pairs += len(matches)

    if row_count != len(ordered_predictions):
        raise ValueError(
            f"Quantidade de previsões aplicadas ({row_count}) difere do arquivo de previsões ({len(ordered_predictions)})."
        )

    summary = workbook.create_sheet("Resumo Guilherme")
    summary_rows = [
        ("Campo", "Definição / resultado"),
        ("Previsão principal", f"Guilherme | {args.model_label}; estimativa experimental do alvo proxy 90% × OFERTA; sem multiplicador adicional."),
        ("Cálculo direto", "Guilherme | cálculo aritmético de 90% × OFERTA; não é previsão do modelo."),
        ("Avaliação", "Referência recebida na planilha; não foi calculada pela API."),
        ("Regra de cor", f"Verde: previsão a até {args.tolerance_percent:g}% de ao menos um colega. Amarelo: nenhum colega dentro da tolerância."),
        ("Itens com ao menos uma correspondência", f"{matched_rows} de {row_count}"),
        ("Correspondências previsão-colega", str(matched_peer_pairs)),
        ("Alvo treinado", "0,90 × preço anunciado; não equivale a avaliação de mercado nem a valor de venda confirmado."),
        ("Limite", "A cor mede proximidade aos resultados dos colegas, não comprova acurácia perante um valor real independente."),
    ]
    for values in summary_rows:
        summary.append(values)
    for cell in summary[1]:
        cell.fill = dark_blue
        cell.font = Font(color="FFFFFF", bold=True)
    summary.column_dimensions["A"].width = 44
    summary.column_dimensions["B"].width = 118
    for row in summary.iter_rows():
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    sheet.freeze_panes = f"A{header + 1}"
    sheet.row_dimensions[header].height = 62
    for col, width in ((output_col, 62), (direct_col, 58), (match_col, 65)):
        sheet.column_dimensions[get_column_letter(col)].width = width
    for row in range(header + 1, sheet.max_row + 1):
        sheet.cell(row, match_col).alignment = Alignment(wrap_text=True, vertical="top")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)
    print(f"Arquivo gerado: {output_path}")
    print(f"Previsões preenchidas: {row_count}; com ao menos uma correspondência: {matched_rows}.")


if __name__ == "__main__":
    main()
