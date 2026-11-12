from __future__ import annotations

import os
import logging
import io
import math
import re
import unicodedata
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Body, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from pydantic import BaseModel, ConfigDict, Field, field_validator

import store
from model_runtime import MODEL_ID, TARGET_DESCRIPTION, load_model, predict_many

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("hedonic-api")
bundle, model_report = load_model()
enabled = os.environ.get("ENABLE_EXPERIMENTAL_HEDONIC_AVM", "true").lower() == "true"
peer_alignment_enabled = False  # v4 never calibrates against peer outputs.
offer_calibration_enabled = os.environ.get("ENABLE_OFFER_CALIBRATION", "true").lower() == "true"
base_model_id = MODEL_ID.removesuffix("_offer_calibrated")
active_model_id = f"{base_model_id}_{'offer_calibrated' if offer_calibration_enabled else 'raw'}"
database_ready = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    global database_ready
    database_ready = store.initialize_store()
    logger.info("Supabase/PostgreSQL persistence ready=%s", database_ready)
    yield


app = FastAPI(
    title="AVM Hedônico Experimental — Challenger",
    description=(
        "Sistema independente experimental. Estima o valor integral de oferta/anúncio; "
        "não é avaliação de mercado, avaliação CAIXA nem decisão de crédito."
    ),
    version=active_model_id,
    lifespan=lifespan,
)
origins = [value.strip() for value in os.environ.get("AVM_CORS_ORIGINS", "*").split(",") if value.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials="*" not in origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class HedonicApartmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    area_privativa_m2: float = Field(ge=35, le=1000)
    idade_anos: int = Field(ge=0, le=20)
    valor_oferta_brl: float | None = Field(default=None, gt=0)
    quartos: int | None = Field(default=None, ge=0, le=10)
    banheiros: int | None = Field(default=None, ge=0, le=10)
    vagas: int | None = Field(default=None, ge=0, le=10)
    elevador: int | None = Field(default=None, ge=0, le=1)
    area_total_m2: float | None = Field(default=None, gt=0, le=2000)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    renda_mediana_mensal_brl: float | None = Field(default=None, gt=0)
    renda_media_mensal_brl: float | None = Field(default=None, gt=0)
    cep: str | None = Field(default=None, max_length=8)
    regiao: str | None = Field(default=None, max_length=60)
    distrito: str | None = Field(default=None, max_length=100)
    setor_censitario: str | None = Field(default=None, max_length=30)
    padrao_iptu: str | None = Field(default=None, max_length=20)

    @field_validator("cep", mode="before")
    @classmethod
    def clean_cep(cls, value: Any) -> Any:
        if value in (None, ""):
            return None
        digits = "".join(char for char in str(value) if char.isdigit())
        if len(digits) not in {5, 8}:
            raise ValueError("CEP deve conter 5 ou 8 dígitos.")
        return digits


def _as_dict(item: HedonicApartmentInput) -> dict[str, Any]:
    return item.model_dump()


def _normalized_header(value: Any) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(character for character in value if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def _cell_number(value: Any) -> float | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, str):
        value = value.strip().replace("R$", "").replace(" ", "")
        if "," in value and "." in value:
            value = value.replace(".", "").replace(",", ".")
        elif "," in value:
            value = value.replace(",", ".")
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _worksheet_columns(sheet) -> tuple[int, dict[str, int]]:
    aliases = {
        "area_privativa": {"area_privativa", "area_privativa_m2"},
        "idade": {"idade", "idade_anos"},
        "distrito": {"bairro_subdistrito", "bairro", "distrito"},
        "cep": {"cep"}, "quartos": {"quartos", "dormitorios"},
        "banheiros": {"banheiros", "banheiro"}, "vagas": {"vagas", "vagas_de_garagem"},
        "elevador": {"elevador"}, "area_total": {"area_total", "area_total_m2"},
        "offer_output": {"valor_estimado_r", "valor_estimado"},
        "unit_output": {"valor_unitario_r_m", "valor_unitario_r_m2", "valor_unitario_r_m_2"},
        "method_output": {"metodologia"}, "notes_output": {"observacoes", "observacao"},
    }
    for row_number in range(1, min(sheet.max_row, 30) + 1):
        normalized = {
            _normalized_header(sheet.cell(row_number, column).value): column
            for column in range(1, sheet.max_column + 1)
            if sheet.cell(row_number, column).value is not None
        }
        resolved = {
            key: next((normalized[name] for name in names if name in normalized), None)
            for key, names in aliases.items()
        }
        required = ("area_privativa", "idade", "offer_output", "unit_output", "method_output", "notes_output")
        if all(resolved[key] for key in required):
            return row_number, resolved
    raise HTTPException(422, "A planilha precisa conter AREA PRIVATIVA, idade e as quatro colunas de saída do modelo TESTE.")


def _predict(properties: list[dict[str, Any]]) -> list[float]:
    if not enabled:
        raise HTTPException(503, "Challenger desativado. Ative ENABLE_EXPERIMENTAL_HEDONIC_AVM=true após revisão.")
    try:
        return predict_many(bundle, properties, apply_peer_alignment=peer_alignment_enabled, apply_offer_calibration=offer_calibration_enabled)
    except (ValueError, TypeError, OverflowError) as error:
        logger.exception("Falha na inferência hedônica")
        raise HTTPException(422, "Não foi possível produzir uma estimativa com os atributos enviados.") from error


def _responses(properties: list[dict[str, Any]], predictions: list[float]) -> list[dict[str, Any]]:
    ids = store.save_predictions(properties, predictions, active_model_id)
    return [
        {
            "registro_id": record_id,
            "model_id": active_model_id,
            "status": "estimado · experimental",
            "alvo": TARGET_DESCRIPTION,
            "estimativa_alvo_brl": value,
            "calibracao_oferta_habilitada": offer_calibration_enabled,
            "fator_calibracao_oferta": bundle.get("offer_calibration_factor") if offer_calibration_enabled else None,
            "metodologia": (
                "Ridge hedonic splines com calibracao de oferta v4"
                if offer_calibration_enabled else "Ridge hedonic splines sem calibracao v4"
            ),
            "observacao": "Fator estimado em amostra separada de ofertas; nao representa avaliacao CAIXA.",
            "persistido_supabase": record_id is not None,
        }
        for record_id, value in zip(ids, predictions)
    ]


@app.get("/")
def health():
    return {
        "status": "experimental" if enabled else "desativado",
        "model_id": active_model_id,
        "modelo_carregado": True,
        "habilitado": enabled,
        "alinhamento_com_pares_habilitado": peer_alignment_enabled,
        "calibracao_oferta_habilitada": offer_calibration_enabled,
        "persistencia_supabase": database_ready,
        "alvo": TARGET_DESCRIPTION,
        "aprovado_para_avaliacao_operacional": False,
    }


@app.get("/modelo/info")
def model_info():
    return {
        "model_id": active_model_id,
        "status": "experimental_peer_aligned_not_approved_for_operational_use" if peer_alignment_enabled else "experimental_challenger_not_approved_for_operational_use",
        "habilitado": enabled,
        "alinhamento_com_pares_habilitado": peer_alignment_enabled,
        "calibracao_oferta_habilitada": offer_calibration_enabled,
        "calibracao_alinhamento": model_report.get("peer_alignment") if peer_alignment_enabled else None,
        "equacao": model_report["method"]["equation"],
        "metricas_teste_geografico": model_report["independent_geographic_test"],
        "runtime_versions": model_report["runtime_versions"],
        "alvo": TARGET_DESCRIPTION,
        "aprovado_para_avaliacao_operacional": False,
    }


@app.get("/history")
def prediction_history(limit: int = Query(50, ge=1, le=100)):
    if not database_ready:
        return {"database": "unavailable", "predictions": []}
    return {"database": "postgresql", "predictions": store.list_predictions(limit)}


@app.post("/predict")
def predict(item: HedonicApartmentInput):
    properties = [_as_dict(item)]
    predictions = _predict(properties)
    return _responses(properties, predictions)[0]


@app.post("/predict/batch")
def predict_batch(items: list[HedonicApartmentInput] = Body(...)):
    if not items or len(items) > 500:
        raise HTTPException(422, "Envie de 1 a 500 imóveis por lote.")
    properties = [_as_dict(item) for item in items]
    predictions = _predict(properties)
    return {
        "model_id": active_model_id,
        "status": "experimental",
        "alvo": TARGET_DESCRIPTION,
        "estimativas": _responses(properties, predictions),
    }


@app.post("/predict/upload", response_class=Response)
async def predict_upload(file: UploadFile = File(...)):
    if not file.filename or not file.filename.casefold().endswith(".xlsx"):
        raise HTTPException(422, "Envie uma planilha .xlsx no formato TESTE.")
    content = await file.read()
    if not content or len(content) > 20 * 1024 * 1024:
        raise HTTPException(422, "A planilha está vazia ou excede o limite de 20 MB.")
    try:
        workbook = load_workbook(io.BytesIO(content))
    except Exception as error:
        raise HTTPException(422, "Não foi possível abrir a planilha XLSX enviada.") from error
    sheet = workbook["teste"] if "teste" in workbook.sheetnames else workbook[workbook.sheetnames[0]]
    header_row, columns = _worksheet_columns(sheet)
    row_data: list[tuple[int, dict[str, Any]]] = []
    validation_errors = 0
    for row_number in range(header_row + 1, sheet.max_row + 1):
        if not any(sheet.cell(row_number, column).value is not None for column in range(1, sheet.max_column + 1)):
            continue
        area = _cell_number(sheet.cell(row_number, columns["area_privativa"]).value)
        age = _cell_number(sheet.cell(row_number, columns["idade"]).value)
        if area is None and age is None:
            continue
        reasons = []
        if area is None or not 35 <= area <= 1000:
            reasons.append("área privativa ausente ou fora de 35 a 1.000 m²")
        if age is None or not 0 <= age <= 20 or int(age) != age:
            reasons.append("idade ausente ou fora de 0 a 20 anos")
        item = {
            "area_privativa_m2": area,
            "idade_anos": int(age) if age is not None and int(age) == age else None,
            "quartos": _cell_number(sheet.cell(row_number, columns["quartos"]).value) if columns["quartos"] else None,
            "banheiros": _cell_number(sheet.cell(row_number, columns["banheiros"]).value) if columns["banheiros"] else None,
            "vagas": _cell_number(sheet.cell(row_number, columns["vagas"]).value) if columns["vagas"] else None,
            "area_total_m2": _cell_number(sheet.cell(row_number, columns["area_total"]).value) if columns["area_total"] else None,
            "distrito": str(sheet.cell(row_number, columns["distrito"]).value).strip() if columns["distrito"] and sheet.cell(row_number, columns["distrito"]).value else None,
            "cep": str(sheet.cell(row_number, columns["cep"]).value).strip() if columns["cep"] and sheet.cell(row_number, columns["cep"]).value else None,
        }
        if columns["elevador"]:
            raw_lift = sheet.cell(row_number, columns["elevador"]).value
            lift = _cell_number(raw_lift)
            if lift == 2:
                item["elevador"] = 1
            elif lift == 0:
                item["elevador"] = 0
            elif isinstance(raw_lift, str) and raw_lift.strip().casefold() in {"sim", "s", "yes"}:
                item["elevador"] = 1
            elif isinstance(raw_lift, str) and raw_lift.strip().casefold() in {"nao", "não", "n", "no"}:
                item["elevador"] = 0
            else:
                item["elevador"] = None
        if reasons:
            notes_column = columns["notes_output"]
            sheet.cell(row_number, notes_column, "Sem estimativa: " + "; ".join(reasons))
            validation_errors += 1
        else:
            row_data.append((row_number, item))
    if len(row_data) > 500:
        raise HTTPException(422, "A planilha pode conter no máximo 500 imóveis válidos por processamento.")
    if not row_data:
        raise HTTPException(422, "Nenhuma linha válida para estimar foi encontrada na planilha.")
    properties = [item for _, item in row_data]
    predictions = _predict(properties)
    _responses(properties, predictions)
    for (row_number, item), prediction in zip(row_data, predictions):
        area = item["area_privativa_m2"]
        sheet.cell(row_number, columns["offer_output"], prediction).number_format = '"R$" #,##0.00'
        sheet.cell(row_number, columns["unit_output"], round(prediction / area, 2)).number_format = '"R$" #,##0.00'
        sheet.cell(row_number, columns["method_output"], "Ridge hedonic splines; CEP e distrito; calibracao de oferta v4")
        sheet.cell(row_number, columns["notes_output"], "Estimativa experimental do valor integral de oferta; calibracao v4 habilitada. Nao e avaliacao CAIXA.")
    sheet.freeze_panes = sheet.freeze_panes or f"A{header_row + 1}"
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    return Response(
        content=buffer.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{Path(file.filename).stem}_system2_estimado.xlsx"',
            "X-Estimated-Count": str(len(row_data)),
            "X-Skipped-Count": str(validation_errors),
            "X-Model-Id": active_model_id,
        },
    )


@app.post("/predict/workbook", response_class=Response)
def predict_workbook(items: list[HedonicApartmentInput] = Body(...)):
    if not items or len(items) > 500:
        raise HTTPException(422, "Envie de 1 a 500 imóveis por planilha.")
    properties = [_as_dict(item) for item in items]
    predictions = _predict(properties)
    _responses(properties, predictions)

    headers = [
        "x", "AVALIAÇÃO", "OFERTA", "Endereço", "Complemento", "Andar",
        "Bairro / subdistrito", "CEP", "Município", "Tipologia", "QUARTOS",
        "Banheiros", "VAGAS", "Elevador", "AREA TOTAL", "AREA PRIVATIVA",
        "Fração ideal", "Matrícula n°", "Cartório (ofício)", "Nome do condomínio",
        "Contribuinte (SQL)", "idade", "Valor estimado (R$)",
        "Valor unitário (R$/m²)", "Metodologia", "Observações",
    ]
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "teste"
    sheet.cell(1, 1, "Resultado de precificação de imóveis — challenger hedônico experimental")
    sheet.cell(2, 1, "Alvo estimado: valor integral de oferta/anúncio; não é avaliação de mercado ou avaliação CAIXA.")
    sheet.cell(3, 1, "Campos sem informação foram mantidos vazios; não foram presumidos como zero.")
    sheet.cell(4, 1, "A coluna AVALIAÇÃO é apenas referência e não é usada como entrada do modelo.")
    sheet.cell(5, 1, "As quatro colunas finais registram valor estimado, valor unitário, metodologia e observações.")
    sheet.cell(6, 1, "Este challenger experimental não representa avaliação independente de mercado/CAIXA.")
    for row in range(1, 7):
        sheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=len(headers))
    header_row = 8
    for column, label in enumerate(headers, start=1):
        cell = sheet.cell(header_row, column, label)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="284B63")
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    for column in range(23, 27):
        sheet.cell(header_row, column).fill = PatternFill("solid", fgColor="D9EAD3")
    for index, (item, prediction) in enumerate(zip(properties, predictions), start=1):
        row = header_row + index
        area = item["area_privativa_m2"]
        values = {
            1: index, 3: item.get("valor_oferta_brl"), 8: item.get("cep"),
            11: item.get("quartos"), 12: item.get("banheiros"), 13: item.get("vagas"),
            14: item.get("elevador"), 15: item.get("area_total_m2"), 16: area,
            22: item.get("idade_anos"), 23: prediction,
            24: round(prediction / area, 2),
            25: "Ridge hedonic splines com calibracao de oferta v4" if offer_calibration_enabled else "Ridge hedonic splines sem calibracao v4",
            26: "Estimativa experimental do valor integral de oferta. Fator aprendido em ofertas separadas; nao e avaliacao CAIXA.",
        }
        for column, value in values.items():
            if value is not None:
                sheet.cell(row, column, value)
        sheet.cell(row, 23).number_format = '"R$" #,##0.00'
        sheet.cell(row, 24).number_format = '"R$" #,##0.00'
        for column in (25, 26):
            sheet.cell(row, column).alignment = Alignment(wrap_text=True, vertical="top")
    sheet.freeze_panes = "A9"
    sheet.auto_filter.ref = f"A{header_row}:Z{header_row + len(items)}"
    for column, width in {"A": 8, "B": 16, "C": 16, "D": 42, "G": 24, "H": 14,
                          "K": 11, "L": 12, "M": 10, "N": 12, "O": 14, "P": 16,
                          "V": 10, "W": 20, "X": 22, "Y": 45, "Z": 64}.items():
        sheet.column_dimensions[column].width = width
    import io
    buffer = io.BytesIO()
    workbook.save(buffer)
    return Response(
        content=buffer.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="resultado_hedonic_challenger.xlsx"'},
    )
