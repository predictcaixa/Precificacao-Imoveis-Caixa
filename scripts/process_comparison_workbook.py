"""Run the comparison workbook through the live API and save an output workbook."""

from __future__ import annotations

import argparse
import json
import math
import re
from datetime import date
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import unicodedata

from openpyxl import load_workbook
from openpyxl.styles import Font

HEADERS = [
    "area_privativa_m2", "idade_anos", "valor_oferta_brl", "quartos", "banheiros", "vagas",
    "elevador", "area_total_m2", "renda_mediana_mensal_brl",
    "renda_media_mensal_brl", "cep", "regiao", "distrito",
    "setor_censitario", "padrao_iptu", "imovel", "endereco", "bairro",
]
STATUS_VALIDATION_ERROR = "erro de valida\u00e7\u00e3o"
STATUS_PREDICTION_ERROR = "erro de previs\u00e3o"
STATUS_EXPERIMENTAL = "estimado \u00b7 experimental"


def api_json(api_url: str, path: str, payload: Any = None, method: str = "GET") -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        f"{api_url.rstrip('/')}{path}",
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method=method,
    )
    try:
        with urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API respondeu HTTP {error.code} em {path}: {detail}") from error


def text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def normalize_header(value: Any) -> str:
    normalized = unicodedata.normalize("NFD", text(value))
    normalized = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    key = re.sub(r"[^a-zA-Z0-9]+", "_", normalized.lower()).strip("_")
    return {"valor_oferta": "valor_oferta_brl", "oferta": "valor_oferta_brl",
            "valor_oferta_r": "valor_oferta_brl", "preco_oferta": "valor_oferta_brl",
            "preco_de_oferta": "valor_oferta_brl", "preco_anunciado": "valor_oferta_brl",
            "oferta_r": "valor_oferta_brl"}.get(key, key)


def number(value: Any) -> float | None:
    if value is None or not text(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raw = text(value).casefold()
    if raw in {"n\u00e3o informado", "nao informado", "n/i", "n.a.", "-"}:
        return None
    raw = raw.replace("m\u00b2", "").replace("r$", "").replace(" ", "")
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        raw = raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def age_from_year(value: Any, reference_year: int) -> int | None:
    match = re.search(r"\b(?:19|20)\d{2}\b", text(value))
    return reference_year - int(match.group()) if match else None


def find_column(columns: dict[str, int], *names: str) -> int | None:
    return next((columns[name] for name in names if name in columns), None)


def cell_value(sheet: Any, row: int, column: int | None) -> Any:
    return sheet.cell(row, column).value if column is not None else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("dados/derivados"))
    parser.add_argument("--api-url", default="http://127.0.0.1:8001")
    parser.add_argument("--model", choices=("xgboost", "catboost", "random_forest"), default="catboost")
    parser.add_argument("--tag", default="", help="Sufixo para não sobrescrever outra execução, por exemplo catboost.")
    args = parser.parse_args()
    input_path = args.input.resolve()
    out_dir = args.output_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"_{args.tag}" if args.tag else ""
    normalized_path = out_dir / f"{input_path.stem}{suffix}_input_avm.xlsx"
    result_path = out_dir / f"{input_path.stem}{suffix}_resultado_avm.xlsx"

    workbook = load_workbook(input_path)
    source = workbook[workbook.sheetnames[0]]
    header_row = next((
        row for row in range(1, min(source.max_row, 30) + 1)
        if "area_privativa" in {
            normalize_header(source.cell(row, col).value)
            for col in range(1, source.max_column + 1)
        }
        and any(
            normalize_header(source.cell(row, col).value) in {"idade", "idade_anos", "ano_construcao", "ano_da_construcao"}
            for col in range(1, source.max_column + 1)
        )
    ), None)
    if header_row is None:
        raise ValueError("Cabeçalho de imóveis não encontrado na planilha de entrada.")

    columns = {
        normalize_header(source.cell(header_row, col).value): col
        for col in range(1, source.max_column + 1)
        if source.cell(header_row, col).value is not None
    }
    area_column = find_column(columns, "area_privativa", "area_privativa_m2")
    total_area_column = find_column(columns, "area_total", "area_total_m2")
    age_column = find_column(columns, "idade_anos", "idade")
    year_column = find_column(columns, "ano_construcao", "ano_da_construcao", "ano_construcao_averbacao")
    offer_column = find_column(columns, "valor_oferta_brl", "valor_oferta", "oferta", "preco_oferta")
    item_column = find_column(columns, "imovel", "apartamento", "x") or 1
    address_column = find_column(columns, "endereco", "endereco_completo")
    neighborhood_column = find_column(columns, "bairro_subdistrito", "bairro", "distrito")
    zip_column = find_column(columns, "cep")
    bedrooms_column = find_column(columns, "quartos", "dormitorios")
    bathrooms_column = find_column(columns, "banheiros", "banheiro")
    parking_column = find_column(columns, "vagas", "vagas_de_garagem")
    lift_column = find_column(columns, "elevador")
    value_output_column = find_column(columns, "valor_estimado_r", "valor_r", "estimativa_alvo_brl")
    unit_output_column = find_column(columns, "valor_unitario_r_m", "valor_unitario_r_m2", "valor_m2")
    method_output_column = find_column(columns, "metodologia")
    notes_output_column = find_column(columns, "observacoes", "observacao")
    if not all((area_column, age_column or year_column, value_output_column, unit_output_column, method_output_column, notes_output_column)):
        raise ValueError("A planilha precisa ter area privativa, idade/ano e as quatro colunas de saida.")

    records: list[dict[str, Any]] = []
    valid_indices: list[int] = []
    statuses: list[dict[str, Any]] = []
    reference_year = date.today().year
    for row_idx in range(header_row + 1, source.max_row + 1):
        if not any(source.cell(row_idx, col).value is not None for col in range(1, source.max_column + 1)):
            continue
        area = number(cell_value(source, row_idx, area_column))
        age = number(cell_value(source, row_idx, age_column)) if age_column else age_from_year(cell_value(source, row_idx, year_column), reference_year)
        raw_elevator = number(cell_value(source, row_idx, lift_column))
        # TESTE.xlsx uses 1 = not confirmed and 2 = elevator confirmed (see its legend).
        elevator = 1 if raw_elevator == 2 else (0 if raw_elevator == 0 else None)
        raw_offer = cell_value(source, row_idx, offer_column)
        offer = number(raw_offer)
        address = text(cell_value(source, row_idx, address_column)) or None
        neighborhood = text(cell_value(source, row_idx, neighborhood_column)) or None
        if area is None and not address and cell_value(source, row_idx, item_column) is None:
            continue
        item: dict[str, Any] = {
            "area_privativa_m2": area,
            "idade_anos": age,
            "valor_oferta_brl": offer,
            "quartos": number(cell_value(source, row_idx, bedrooms_column)),
            "banheiros": number(cell_value(source, row_idx, bathrooms_column)),
            "vagas": number(cell_value(source, row_idx, parking_column)),
            "elevador": elevator,
            "area_total_m2": number(cell_value(source, row_idx, total_area_column)),
            "regiao": None,
            "distrito": neighborhood,
            "cep": text(cell_value(source, row_idx, zip_column)).replace("-", "") or None,
            "source_row": row_idx,
            "imovel": cell_value(source, row_idx, item_column),
            "endereco": address,
            "bairro": neighborhood,
        }
        reason = ""
        if raw_offer not in (None, "") and (offer is None or not math.isfinite(offer) or offer <= 0):
            reason = "Valor de oferta inválido; informe um valor positivo."
        elif offer is None and (area is None or not 35 <= area <= 1000):
            reason = "Área privativa ausente ou fora do intervalo aceito (35–1.000 m²)."
        elif offer is None and age is None:
            reason = "Idade/ano da construção não informado; idade não pode ser calculada sem imputação."
        elif offer is None and not 0 <= age <= 20:
            reason = "Idade calculada fora do intervalo aceito (0–20 anos)."
        if reason:
            statuses.append({"row": row_idx, "item": item, "error": reason, "prediction": None, "status": STATUS_VALIDATION_ERROR})
        else:
            valid_indices.append(len(statuses))
            payload = {"valor_oferta_brl": offer} if offer is not None else {
                key: item.get(key)
                for key in (
                    "area_privativa_m2", "idade_anos", "quartos", "banheiros", "vagas",
                    "elevador", "area_total_m2", "cep", "regiao", "distrito",
                )
            }
            statuses.append({"row": row_idx, "item": item, "payload": payload, "error": "", "prediction": None, "status": "aguardando previs\u00e3o"})
            records.append(payload)

    api_root = args.api_url.rstrip("/")
    imported = api_json(api_root, "/avm/imports", {
        "file_name": input_path.name,
        "model": args.model,
        "total_rows": len(statuses),
    }, "POST")
    import_id = imported["id"]
    selected = "default model"
    algorithm = args.model
    try:
        if records:
            api_result = api_json(api_root, f"/predict/batch?modelo={args.model}", records, "POST")
            estimates = api_result.get("estimativas", [])
            predictions = [
                float(item["estimativa_alvo_brl"])
                for item in estimates
            ]
            if len(predictions) != len(records):
                raise RuntimeError("API returned an unexpected number of predictions")
            selected = api_result.get("modelo", selected)
            algorithm = api_result.get("algoritmo", algorithm)
            for status_idx, prediction, estimate in zip(valid_indices, predictions, estimates):
                statuses[status_idx]["prediction"] = prediction
                statuses[status_idx]["status"] = (
                    "calculado · oferta × 0,9"
                    if estimate.get("status") == "calculado"
                    else STATUS_EXPERIMENTAL
                )
                statuses[status_idx]["methodology"] = estimate.get("metodologia")
                statuses[status_idx]["raw_prediction"] = estimate.get("estimativa_modelo_bruta_brl")
                statuses[status_idx]["adjustment_factor"] = estimate.get("fator_ajuste_saida", 1.0)
        rows_to_save = [
            {
                "source_row": status["row"],
                "source_data": status["item"],
                "prediction": status["prediction"],
                "status": status["status"],
                "error": status["error"] or None,
            }
            for status in statuses
        ]
        for offset in range(0, len(rows_to_save), 500):
            api_json(
                api_root,
                f"/avm/imports/{import_id}/rows",
                rows_to_save[offset:offset + 500],
                "POST",
            )
        api_json(api_root, f"/avm/imports/{import_id}", {"status": "completed"}, "PATCH")
    except Exception as error:
        try:
            api_json(
                api_root,
                f"/avm/imports/{import_id}",
                {"status": "failed", "error": str(error)[:2000]},
                "PATCH",
            )
        except Exception:
            pass
        raise

    # Build an upload-compatible first sheet while keeping the source form as a tab.
    adapted = load_workbook(input_path)
    upload = adapted.create_sheet("AVM Input", 0)
    upload.append(HEADERS)
    for status in statuses:
        item = status["item"]
        upload.append([
            item.get("area_privativa_m2"), item.get("idade_anos"), item.get("valor_oferta_brl"),
            item.get("quartos"), item.get("banheiros"), item.get("vagas"),
            item.get("elevador"), item.get("area_total_m2"), None, None, None, None,
            item.get("distrito"), None, None, item.get("imovel"), item.get("endereco"), item.get("bairro"),
        ])
    adapted.save(normalized_path)

    # Fill the four designated output columns in a copy of the original styled form.
    result_book = load_workbook(input_path)
    result_sheet = result_book[result_book.sheetnames[0]]
    method = f"AVM experimental ({algorithm}, {selected}); alvo proxy de 90% do preço de oferta"
    scored = {status["row"]: status for status in statuses}
    for row_idx, status in scored.items():
        estimate = status["prediction"]
        area = status["item"].get("area_privativa_m2")
        result_sheet.cell(row_idx, value_output_column).value = estimate
        result_sheet.cell(row_idx, unit_output_column).value = round(estimate / area, 2) if estimate is not None and area else None
        result_sheet.cell(row_idx, method_output_column).value = status.get("methodology") or (method if estimate is not None else "Não estimado pelo modelo")
        note = (
            "Cálculo direto: 90% da oferta informada; não é avaliação independente de mercado/CAIXA."
            if status["status"] == "calculado · oferta × 0,9"
            else "Estimativa experimental do alvo 90% do preço de oferta; não é avaliação de mercado/CAIXA."
        )
        if status["item"].get("elevador") is None:
            note += " Elevador não confirmado na matrícula foi tratado como ausente, sem assumir ausência do equipamento."
        adjustment_factor = status.get("adjustment_factor", 1.0)
        if estimate is not None and adjustment_factor != 1.0:
            raw_prediction = status.get("raw_prediction")
            note += (
                " Ajuste exploratório de alinhamento com as referências Januario/Análise: "
                f"valor bruto R$ {raw_prediction:,.2f} × {adjustment_factor:.4f}. "
                "O ajuste aproxima a média das duas equipes nesta amostra, mas não melhora "
                "o MAPE contra AVALIAÇÃO."
            )
        if status["error"]:
            note += " " + status["error"]
        result_sheet.cell(row_idx, notes_output_column).value = note
        for col in (value_output_column, unit_output_column, method_output_column, notes_output_column):
            result_sheet.cell(row_idx, col).font = Font(name="Calibri", size=10, color="C00000" if estimate is None else "000000")
    result_book.save(result_path)

    estimated = sum(status["prediction"] is not None for status in statuses)
    print(f"Modelo via API original: {algorithm} ({selected})")
    print(f"Linhas estimadas: {estimated}/{len(statuses)}; sem estimativa: {len(statuses) - estimated}")
    print(f"Input ajustado: {normalized_path}")
    print(f"Importacao registrada: {import_id}")
    print(f"Resultado no formato original: {result_path}")


if __name__ == "__main__":
    main()
