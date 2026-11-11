"""Upload the 30.10.2026 source workbook through the AVM API and export results."""

from __future__ import annotations

import argparse
import json
import math
import re
import unicodedata
from copy import copy
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from openpyxl import load_workbook


ALIASES = {
    "area_priv": "area_privativa_m2",
    "idade": "idade_anos",
    "area_total": "area_total_m2",
    "renda_mediana_ibge_2022_r": "renda_mediana_mensal_brl",
    "renda_media_ibge_2022_r": "renda_media_mensal_brl",
    "setor_censitario_2022": "setor_censitario",
    "valor_oferta": "valor_oferta_brl",
    "oferta": "valor_oferta_brl",
    "valor_oferta_r": "valor_oferta_brl",
    "preco_oferta": "valor_oferta_brl",
    "preco_de_oferta": "valor_oferta_brl",
    "preco_anunciado": "valor_oferta_brl",
    "oferta_r": "valor_oferta_brl",
}
NUMERIC_RULES = {
    "area_privativa_m2": (True, 35, 1000, False),
    "idade_anos": (True, 0, 20, True),
    "valor_oferta_brl": (False, 5e-324, None, False),
    "quartos": (False, 0, 10, True),
    "banheiros": (False, 0, 10, True),
    "vagas": (False, 0, 10, True),
    "elevador": (False, 0, 1, True),
    "area_total_m2": (False, 5e-324, 2000, False),
    "renda_mediana_mensal_brl": (False, 5e-324, None, False),
    "renda_media_mensal_brl": (False, 5e-324, None, False),
}
REGIONS = {"Centro", "Zona Leste", "Zona Leste²", "Zona Norte", "Zona Oeste", "Zona Sul"}
STATUS_INVALID = "erro de valida\u00e7\u00e3o"
STATUS_PREDICTION_ERROR = "erro de previs\u00e3o"
STATUS_ESTIMATED = "estimado \u00b7 experimental"


def normalize_header(value: Any) -> str:
    value = unicodedata.normalize("NFD", str(value or ""))
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value.lower()).strip("_")
    return ALIASES.get(value, value)


def number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value) if value == value else None
    raw = str(value).strip().replace(" ", "")
    raw = re.sub(r"^R\$", "", raw, flags=re.IGNORECASE)
    if not raw:
        return None
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return math.nan


def json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


def validate(row: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    raw_offer = row.get("valor_oferta_brl")
    offer = number(raw_offer)
    if offer is not None and math.isfinite(offer) and offer > 0:
        return {"valor_oferta_brl": offer}, []

    if raw_offer not in (None, ""):
        return {}, ["valor_oferta_brl invÃ¡lido; informe um valor positivo ou deixe o campo vazio para usar o AVM"]

    payload: dict[str, Any] = {}
    errors: list[str] = []
    for field, (required, minimum, maximum, integer) in NUMERIC_RULES.items():
        value = number(row.get(field))
        if value is None:
            if required:
                errors.append(f"{field} obrigat\u00f3rio")
            else:
                payload[field] = None
            continue
        if not math.isfinite(value):
            errors.append(f"{field} inv\u00e1lido")
            continue
        if value < minimum or (maximum is not None and value > maximum):
            errors.append(f"{field} fora do intervalo permitido")
            continue
        if integer and not value.is_integer():
            errors.append(f"{field} deve ser inteiro")
            continue
        payload[field] = int(value) if integer else value

    for field in ("cep", "regiao", "distrito", "setor_censitario", "padrao_iptu"):
        raw = row.get(field)
        value = "" if raw is None else str(raw).strip()
        if field == "cep":
            if not value:
                payload[field] = None
                continue
            digits = re.sub(r"\D", "", value)
            if len(digits) == 7:
                digits = digits.zfill(8)
            if len(digits) not in {5, 8}:
                errors.append("cep deve conter 5 ou 8 d\u00edgitos")
            else:
                payload[field] = digits
        elif field == "regiao":
            if not value:
                payload[field] = None
            elif value not in REGIONS:
                errors.append("regiao n\u00e3o reconhecida")
            else:
                payload[field] = value
        else:
            max_length = 100 if field == "distrito" else 30 if field == "setor_censitario" else 20
            if len(value) > max_length:
                errors.append(f"{field} excede {max_length} caracteres")
            else:
                payload[field] = value or None
    return payload, errors


def api_json(api_url: str, path: str, payload: Any = None, method: str = "GET") -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        f"{api_url.rstrip('/')}{path}",
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method=method,
    )
    with urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, nargs="?", default=Path("dados/30.10.2026.xlsx"))
    parser.add_argument("--output", type=Path, default=Path("dados/derivados/30.10.2026_resultado_avm.xlsx"))
    parser.add_argument("--api-url", default="http://127.0.0.1:8001")
    args = parser.parse_args()
    input_path = args.input.resolve()
    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    source_book = load_workbook(input_path, read_only=True, data_only=True)
    source = source_book[source_book.sheetnames[0]]
    original_headers = [cell.value for cell in source[1]]
    normalized_headers = [normalize_header(value) for value in original_headers]
    required = {"area_privativa_m2", "idade_anos"}
    if not required.issubset(set(normalized_headers)) and "valor_oferta_brl" not in normalized_headers:
        raise ValueError("A primeira aba precisa conter AREA PRIV. e IDADE ou VALOR OFERTA.")

    statuses: list[dict[str, Any]] = []
    for excel_row, values in enumerate(source.iter_rows(min_row=2, values_only=True), start=2):
        raw_data = {str(header): json_safe(value) for header, value in zip(original_headers, values) if header is not None}
        if not any(value not in (None, "") for value in raw_data.values()):
            continue
        normalized = {
            header: values[index] if index < len(values) else None
            for index, header in enumerate(normalized_headers)
        }
        payload, errors = validate(normalized)
        statuses.append({
            "row": excel_row,
            "source_data": raw_data,
            "payload": payload if not errors else None,
            "prediction": None,
            "error": "; ".join(errors),
            "status": STATUS_INVALID if errors else "aguardando previs\u00e3o",
        })
    source_book.close()

    valid_indices = [index for index, item in enumerate(statuses) if item["payload"] is not None]
    print(f"Linhas lidas: {len(statuses)}; candidatas a previsao: {len(valid_indices)}; invalidas: {len(statuses)-len(valid_indices)}", flush=True)
    imported = api_json(args.api_url, "/avm/imports", {
        "file_name": input_path.name,
        "model": "xgboost",
        "total_rows": len(statuses),
    }, "POST")
    import_id = imported["id"]
    try:
        for start in range(0, len(statuses), 500):
            end = min(start + 500, len(statuses))
            batch_indices = [index for index in range(start, end) if statuses[index]["payload"] is not None]
            if batch_indices:
                try:
                    result = api_json(
                        args.api_url,
                        "/predict/batch",
                        [statuses[index]["payload"] for index in batch_indices],
                        "POST",
                    )
                    if len(result.get("estimativas", [])) != len(batch_indices):
                        raise RuntimeError("API returned an unexpected number of predictions")
                    for index, estimate in zip(batch_indices, result["estimativas"]):
                        statuses[index]["prediction"] = float(estimate["estimativa_alvo_brl"])
                        statuses[index]["status"] = (
                            "calculado · oferta × 0,9"
                            if estimate.get("status") == "calculado"
                            else STATUS_ESTIMATED
                        )
                        statuses[index]["methodology"] = estimate.get("metodologia")
                except Exception as error:
                    for index in batch_indices:
                        statuses[index]["status"] = STATUS_PREDICTION_ERROR
                        statuses[index]["error"] = str(error)[:2000]

            rows_to_save = [{
                "source_row": item["row"],
                "source_data": item["source_data"],
                "prediction": item["prediction"],
                "status": item["status"],
                "error": item["error"] or None
            } for item in statuses[start:end]]
            api_json(args.api_url, f"/avm/imports/{import_id}/rows", rows_to_save, "POST")
            print(f"Processadas {end}/{len(statuses)} linhas", flush=True)
        api_json(args.api_url, f"/avm/imports/{import_id}", {"status": "completed"}, "PATCH")
    except Exception as error:
        try:
            api_json(args.api_url, f"/avm/imports/{import_id}", {"status": "failed", "error": str(error)[:2000]}, "PATCH")
        except Exception:
            pass
        raise

    result_book = load_workbook(input_path)
    result_sheet = result_book[result_book.sheetnames[0]]
    first_output_col = result_sheet.max_column + 1
    output_headers = [
        "Valor estimado (R$)",
        "Valor unitário (R$/m²)",
        "Metodologia",
        "Observações",
    ]
    style_source = result_sheet.cell(1, result_sheet.max_column)._style
    for offset, header in enumerate(output_headers):
        cell = result_sheet.cell(1, first_output_col + offset, header)
        if style_source:
            cell._style = copy(style_source)
    method = "AVM experimental (XGBoost, xgboost_depth_6); alvo proxy 90% do preço de oferta"
    for item in statuses:
        row = item["row"]
        estimate = item["prediction"]
        area = number(item["source_data"].get("AREA PRIV."))
        values = [
            estimate,
            round(estimate / area, 2) if estimate is not None and area else None,
            item.get("methodology") or (method if estimate is not None else "Não estimado pelo modelo"),
            item["error"] or (
                "Cálculo direto: 90% da oferta informada; não é avaliação independente de mercado/CAIXA."
                if item["status"] == "calculado · oferta × 0,9"
                else "Estimativa experimental do alvo 90% do preço de oferta; não é avaliação de mercado/CAIXA."
            ),
        ]
        for offset, value in enumerate(values):
            cell = result_sheet.cell(row, first_output_col + offset, value)
            if offset in (0, 1) and value is not None:
                cell.number_format = '"R$" #,##0.00'
    for column in range(first_output_col, first_output_col + 4):
        result_sheet.column_dimensions[result_sheet.cell(1, column).column_letter].width = 48 if column >= first_output_col + 2 else 24
    result_book.save(output_path)

    estimated = sum(item["prediction"] is not None for item in statuses)
    print(f"Modelo: xgboost_depth_6; estimadas: {estimated}/{len(statuses)}; sem estimativa: {len(statuses)-estimated}")
    print(f"Importacao: {import_id}")
    print(f"Banco atual: {api_json(args.api_url, '/avm/imports?limit=1').get('database')}")
    print(f"Resultado: {output_path}")


if __name__ == "__main__":
    main()
