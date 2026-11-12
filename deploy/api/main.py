"""
main.py — API REST de Precificação de Imóveis
==============================================
Endpoints:
  GET  /                         → interface web
  GET  /health                   → health check
  POST /predict                  → previsão experimental do alvo 90% da oferta
  POST /predict/batch            → previsão experimental em lote
  POST /predict/workbook         → lote manual com saída XLSX no layout TESTE
  POST /referencia/estimativa    → comparador exploratório, não operacional
  GET  /regioes/stats            → suspenso até validação
  GET  /modelo/info              → estado da validação
  POST /relatorio                → suspenso até validação
  GET  /docs                     → Swagger UI automático

Execução:
  uvicorn main:app --reload --port 8001
"""

import os
import json
from io import BytesIO
import logging
import math
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field, validator
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from scripts.audit_evaluation_csv import DEFAULT_INPUT as EVALUATIONS_PATH
from scripts.audit_evaluation_csv import audit_csv as audit_evaluations_csv
from scripts.audit_caixa_validation import DEFAULT_INPUT as CAIXA_VALIDATION_PATH
from scripts.audit_caixa_validation import audit_dataset as audit_caixa_validation_csv
from scripts.audit_caixa_validation import (
    estimate_caixa_exploratory_reference,
)
from scripts.build_data_catalog import DEFAULT_JSON as DATA_CATALOG_PATH
from scripts.experimental_reference import estimate_reference
from scripts.serve_offer_avm import (
    AvmModelBundle,
    load_avm_models,
    predict_discounted_offer,
    predict_discounted_offers,
)
from scripts import offer_avm_store

CAIXA_VALIDATION_REPORT_PATH = CAIXA_VALIDATION_PATH.with_name(
    "caixa_sp_validacao_audit.json"
)


def _load_caixa_validation_audit() -> dict[str, Any]:
    if CAIXA_VALIDATION_PATH.is_file():
        return audit_caixa_validation_csv(CAIXA_VALIDATION_PATH)
    if CAIXA_VALIDATION_REPORT_PATH.is_file():
        with CAIXA_VALIDATION_REPORT_PATH.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    raise HTTPException(
        503,
        "Resumo agregado da validaÃ§Ã£o CAIXA indisponÃ­vel neste pacote.",
    )

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ─── PATHS ──────────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
FRONTEND_PATH = Path(BASE_DIR) / "index.html"
MODELS_DIR = os.path.join(BASE_DIR, "models")
LEGACY_METADATA_PATH = os.path.join(
    BASE_DIR, "arquivo_legado", "models", "metadata.json"
)
REFERENCE_PATH = os.path.join(MODELS_DIR, "itbi_reference_2026.json")
AVM_REPORT_PATH = os.path.join(MODELS_DIR, "offer_avm", "avm_report.json")
MODEL_NOT_READY_REASON = (
    "O AVM de oferta está disponível apenas como estimativa experimental; "
    "avaliações operacionais, análise regional oficial e relatório permanecem suspensos "
    "até aprovação da proveniência, validação e método."
)

# ─── FASTAPI ─────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="ImóvelML API",
    description=(
        "API de estimativa experimental do alvo de oferta com desconto. "
        "O modelo não foi homologado para avaliação profissional ou decisão de crédito."
    ),
    version="1.0.0",
)

cors_origins = [
    origin.strip()
    for origin in os.environ.get("AVM_CORS_ORIGINS", "*").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials="*" not in cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── CARREGAR MODELO E METADADOS ─────────────────────────────────────────────────
metadata    = None
modelo      = None
reference_rates = None
avm_bundle: Optional[AvmModelBundle] = None
avm_bundles: dict[str, AvmModelBundle] = {}
avm_default_model_key: Optional[str] = None
AVM_OUTPUT_ADJUSTMENT_FACTOR = float(
    os.environ.get("AVM_OUTPUT_ADJUSTMENT_FACTOR", "1.0")
)
if not math.isfinite(AVM_OUTPUT_ADJUSTMENT_FACTOR) or not 0.5 <= AVM_OUTPUT_ADJUSTMENT_FACTOR <= 1.5:
    raise ValueError("AVM_OUTPUT_ADJUSTMENT_FACTOR must be between 0.5 and 1.5.")

REGIOES_VALIDAS = ["centro", "america", "anita", "norte", "sul", "leste", "oeste"]

ALIASES_REGIAO = {
    "leste": "america",
    "zona leste": "america",
    "oeste": "anita",
    "zona oeste": "anita",
    "zona norte": "norte",
    "zona sul": "sul",
}

@app.on_event("startup")
async def carregar_recursos():
    global metadata, reference_rates, avm_bundle, avm_bundles, avm_default_model_key
    offer_avm_store.initialize_store()
    logger.info(
        "Armazenamento de importações conectado: %s.",
        offer_avm_store.backend_name(),
    )
    try:
        with open(LEGACY_METADATA_PATH, "r", encoding="utf-8") as f:
            metadata = json.load(f)
    except FileNotFoundError:
        logger.warning("Metadados do modelo legado não encontrados.")
    try:
        with open(REFERENCE_PATH, "r", encoding="utf-8") as f:
            reference_rates = json.load(f)
    except FileNotFoundError:
        logger.warning(
            "Referência experimental não encontrada; gere com "
            "scripts\\experimental_reference.py."
        )

    if os.path.isfile(AVM_REPORT_PATH):
        avm_bundles = load_avm_models(Path(AVM_REPORT_PATH))
        configured_model = os.environ.get("AVM_DEFAULT_MODEL", "catboost").strip()
        selected_key = _avm_model_key(configured_model)
        if selected_key is None:
            selected_key = _avm_model_key(
                next(iter(avm_bundles.values())).report.get("selected_model")
            )
        avm_bundle = avm_bundles.get(selected_key) if selected_key else None
        if avm_bundle is None:
            raise ValueError(
                "O modelo selecionado no relatório não está entre os artefatos carregados."
            )
        avm_default_model_key = selected_key
        selected_entry = avm_bundle.report.get("available_models", {}).get(selected_key, {})
        logger.info(
            "Modelos AVM experimentais carregados: %s; selecionado=%s.",
            ", ".join(sorted(avm_bundles)),
            selected_entry.get("candidate", avm_bundle.report["selected_model"]),
        )
    else:
        logger.warning(
            "Modelo AVM experimental indisponível: relatório não encontrado em %s.",
            AVM_REPORT_PATH,
        )


# ─── SCHEMAS ────────────────────────────────────────────────────────────────────

class ImovelInput(BaseModel):
    regiao:     str   = Field(..., description="Região do imóvel", example="centro")
    rua:        Optional[str] = Field(None, description="Nome da rua ou avenida específica", example="Avenida Paulista")
    area:       float = Field(..., ge=20, le=1000, description="Área em m²", example=85)
    quartos:    int   = Field(..., ge=1, le=10,   description="Número de quartos", example=3)
    banheiros:  int   = Field(..., ge=1, le=10,   description="Número de banheiros", example=2)
    vagas:      int   = Field(..., ge=0, le=10,   description="Vagas de garagem", example=1)
    idade:      int   = Field(..., ge=0, le=60,   description="Idade do imóvel em anos", example=5)
    suite:      int   = Field(0,  ge=0, le=5,    description="Suítes")
    sacada:     int   = Field(0,  ge=0, le=3,    description="Sacadas/varandas")
    piscina:    int   = Field(0,  ge=0, le=1,    description="Piscina (0=não, 1=sim)")

    @validator("regiao", pre=True)
    def validar_regiao(cls, v):
        if not isinstance(v, str):
            raise ValueError("Região inválida.")
        value = v.strip().lower()
        value = ALIASES_REGIAO.get(value, value)
        if value not in REGIOES_VALIDAS:
            raise ValueError(f"Região inválida. Use: {REGIOES_VALIDAS}")
        return value


REGIOES_AVM = {
    "centro": "Centro",
    "zona leste": "Zona Leste",
    "zona leste²": "Zona Leste²",
    "zona norte": "Zona Norte",
    "zona oeste": "Zona Oeste",
    "zona sul": "Zona Sul",
}


class AvmApartmentInput(BaseModel):
    area_privativa_m2: Optional[float] = Field(None, ge=35, le=1000, example=60)
    idade_anos: Optional[int] = Field(None, ge=0, le=20, example=10)
    valor_oferta_brl: Optional[float] = Field(None, gt=0, example=500000)
    quartos: Optional[int] = Field(None, ge=0, le=10, example=2)
    banheiros: Optional[int] = Field(None, ge=0, le=10, example=2)
    vagas: Optional[int] = Field(None, ge=0, le=10, example=1)
    elevador: Optional[int] = Field(None, ge=0, le=1, example=1)
    area_total_m2: Optional[float] = Field(None, gt=0, le=2000, example=75)
    latitude: Optional[float] = Field(None, ge=-90, le=90, example=-23.55)
    longitude: Optional[float] = Field(None, ge=-180, le=180, example=-46.63)
    renda_mediana_mensal_brl: Optional[float] = Field(None, gt=0, example=5000)
    renda_media_mensal_brl: Optional[float] = Field(None, gt=0, example=7000)
    cep: Optional[str] = Field(None, min_length=5, max_length=8, example="01005")
    regiao: Optional[str] = Field(None, example="Centro")
    distrito: Optional[str] = Field(None, max_length=100, example="Bela Vista")
    setor_censitario: Optional[str] = Field(None, max_length=30)
    padrao_iptu: Optional[str] = Field(None, max_length=20, example="22")

    @validator("regiao", pre=True)
    def normalizar_regiao_avm(cls, value):
        if value is None or value == "":
            return None
        if not isinstance(value, str):
            raise ValueError("Região deve ser texto.")
        normalized = value.strip().casefold()
        if normalized not in REGIOES_AVM:
            raise ValueError(f"Região inválida. Use: {list(REGIOES_AVM.values())}")
        return REGIOES_AVM[normalized]

    @validator("cep", pre=True)
    def validar_cep_avm(cls, value):
        if value is None or value == "":
            return None
        if not isinstance(value, str):
            value = str(value)
        digits = "".join(character for character in value if character.isdigit())
        if len(digits) not in {5, 8}:
            raise ValueError("CEP deve conter os 5 primeiros dígitos ou os 8 dígitos.")
        return digits

    class Config:
        extra = "forbid"


class AvmImportCreateInput(BaseModel):
    file_name: str = Field(..., min_length=1, max_length=255)
    model: Literal["random_forest", "catboost", "xgboost"]
    total_rows: int = Field(..., ge=0, le=50000)


class AvmImportRowInput(BaseModel):
    source_row: int = Field(..., ge=1)
    source_data: Dict[str, Any]
    prediction: Optional[float] = Field(None, ge=0)
    status: Literal[
        "aguardando previsão",
        "erro de validação",
        "erro de previsão",
        "estimado · experimental",
        "calculado · oferta × 0,9",
    ]
    error: Optional[str] = Field(None, max_length=2000)


class AvmImportFinishInput(BaseModel):
    status: Literal["completed", "failed"]
    error: Optional[str] = Field(None, max_length=2000)


def avm_input_as_dict(imovel: AvmApartmentInput) -> Dict[str, Any]:
    model_dump = getattr(imovel, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    return imovel.dict()


def _direct_offer_target(offer_value: float) -> float:
    value = Decimal(str(offer_value)) * Decimal("0.9")
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _require_model_fields(property_data: Dict[str, Any]) -> None:
    if property_data.get("area_privativa_m2") is None:
        raise HTTPException(422, "area_privativa_m2 é obrigatória quando a oferta não foi informada.")
    if property_data.get("idade_anos") is None:
        raise HTTPException(422, "idade_anos é obrigatória quando a oferta não foi informada.")


def _avm_model_key(model_name: object) -> Optional[str]:
    if not isinstance(model_name, str):
        return None
    if model_name.startswith("catboost"):
        return "catboost"
    if model_name.startswith("xgboost"):
        return "xgboost"
    if model_name == "random_forest":
        return "random_forest"
    return None


def _resolve_avm_bundle(model_key: Optional[str]) -> AvmModelBundle:
    if model_key is None:
        if avm_bundle is None:
            raise HTTPException(
                503,
                "Modelo AVM experimental indisponível. Gere os artefatos e o relatório "
                "com scripts\\train_offer_avm.py.",
            )
        return avm_bundle
    if model_key not in {"random_forest", "catboost", "xgboost"}:
        raise HTTPException(422, "Modelo inválido. Use random_forest, catboost ou xgboost.")
    bundle = avm_bundles.get(model_key)
    if bundle is None and avm_bundle is not None and avm_bundle.model_type == model_key:
        bundle = avm_bundle
    if bundle is None:
        raise HTTPException(
            503,
            f"O modelo {model_key} não está carregado. Verifique os artefatos e "
            "dependências do treinamento.",
        )
    return bundle


class ReferenceEstimateInput(BaseModel):
    area_construida_iptu_m2: float = Field(
        ...,
        ge=15,
        le=1000,
        description="Área Construída (m2) do cadastro IPTU, não área privativa/total.",
        example=85,
    )
    cep: Optional[str] = Field(
        None,
        description="CEP completo ou prefixo de 5 dígitos para segmentar comparáveis.",
        example="01005-020",
    )
    codigo_padrao_iptu: Optional[str] = Field(
        None,
        description="Código Padrão (IPTU), de 20 a 25; opcional e não representa padrão IBAPE.",
        example="22",
    )
    confirmar_area_iptu: bool = Field(
        ...,
        description="Confirma que a área informada é a Área Construída cadastral IPTU.",
    )


class CaixaExploratoryEstimateInput(BaseModel):
    area_privativa_m2: float = Field(
        ...,
        ge=10,
        le=2000,
        description=(
            "Área privativa em m² informada para simulação exploratória; "
            "não é convertida de área construída IPTU."
        ),
        example=50,
    )


# ─── ENDPOINTS ──────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def serve_frontend():
    return FileResponse(FRONTEND_PATH, media_type="text/html")


@app.get("/health", tags=["Status"])
def health():
    selected_entry = (
        avm_bundle.report.get("available_models", {}).get(avm_bundle.model_type, {})
        if avm_bundle is not None else {}
    )
    return {
        "status": "experimental" if avm_bundle is not None else "degradado",
        "modelo_carregado": avm_bundle is not None,
        "modelo_avm": (
            selected_entry.get("candidate", avm_bundle.model_type) if avm_bundle is not None else None
        ),
        "predicao_avm_experimental_disponivel": avm_bundle is not None,
        "referencia_experimental_disponivel": reference_rates is not None,
        "estimativa_operacional_aprovada": False,
        "motivo_indisponibilidade": MODEL_NOT_READY_REASON,
        "versao": "1.0.0",
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/avm/imports", tags=["Importações"], status_code=201)
def create_avm_import(import_data: AvmImportCreateInput):
    import_id = offer_avm_store.create_import(
        import_data.file_name, import_data.model, import_data.total_rows
    )
    return {"id": import_id, "status": "processing"}


@app.post("/avm/imports/{import_id}/rows", tags=["Importações"])
def append_avm_import_rows(import_id: str, rows: List[AvmImportRowInput]):
    if not rows:
        raise HTTPException(422, "Informe ao menos uma linha para persistir.")
    if len(rows) > 500:
        raise HTTPException(422, "Cada gravação pode conter no máximo 500 linhas.")
    try:
        serialized_rows = [
            row.model_dump() if hasattr(row, "model_dump") else row.dict()
            for row in rows
        ]
        offer_avm_store.append_import_rows(
            import_id, serialized_rows
        )
    except KeyError as error:
        raise HTTPException(404, error.args[0]) from error
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    return {"import_id": import_id, "saved_rows": len(rows)}


@app.patch("/avm/imports/{import_id}", tags=["Importações"])
def finish_avm_import(import_id: str, finish: AvmImportFinishInput):
    try:
        offer_avm_store.complete_import(
            import_id, finish.status, finish.error
        )
    except KeyError as error:
        raise HTTPException(404, error.args[0]) from error
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    return {"import_id": import_id, "status": finish.status}


@app.get("/avm/imports", tags=["Importações"])
def get_avm_imports(limit: int = Query(50, ge=1, le=100)):
    return {        "imports": offer_avm_store.list_imports(limit),
    "database": offer_avm_store.backend_name(),}


@app.get("/avm/imports/{import_id}/rows", tags=["Importações"])
def get_avm_import_rows(
    import_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=500),
):
    if offer_avm_store.get_import(import_id) is None:
        raise HTTPException(404, "Importação não encontrada.")
    return {
        "import_id": import_id,
        "offset": offset,
        "rows": offer_avm_store.get_import_rows(import_id, offset, limit),
    }


@app.delete("/avm/imports/{import_id}", tags=["Importações"])
def remove_avm_import(import_id: str):
    if not offer_avm_store.delete_import(import_id):
        raise HTTPException(404, "Importação não encontrada.")
    return {"import_id": import_id, "deleted": True}


@app.post("/predict", tags=["Predição"])
def predict(imovel: AvmApartmentInput, modelo: Optional[str] = None):
    property_data = avm_input_as_dict(imovel)
    offer_value = property_data.get("valor_oferta_brl")
    if offer_value is not None:
        return {
            "status": "calculado",
            "modelo": "cálculo direto",
            "algoritmo": "fórmula",
            "alvo": "0,90 × valor de oferta informado",
            "estimativa_alvo_brl": _direct_offer_target(offer_value),
            "metodologia": "Valor de oferta informado × 0,9 (cálculo direto)",
            "aviso": "Resultado aritmético baseado na oferta fornecida; não é avaliação independente de mercado/CAIXA.",
        }

    _require_model_fields(property_data)
    bundle = _resolve_avm_bundle(modelo)
    try:
        raw_prediction = predict_discounted_offer(bundle, property_data)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    prediction = round(raw_prediction * AVM_OUTPUT_ADJUSTMENT_FACTOR, 2)
    model_key = getattr(
        bundle, "model_type", _avm_model_key(bundle.report.get("selected_model"))
    )
    model_entry = bundle.report.get("available_models", {}).get(model_key, {})
    return {
        "status": "experimental",
        "modelo": model_entry.get("candidate", bundle.report["selected_model"]),
        "algoritmo": model_key,
        "alvo": bundle.report["target_definition"],
        "estimativa_alvo_brl": prediction,
        "estimativa_modelo_bruta_brl": raw_prediction,
        "fator_ajuste_saida": AVM_OUTPUT_ADJUSTMENT_FACTOR,
        "metodologia": (
            "AVM experimental; alvo treinado como 0,90 × preço de oferta; "
            f"fator adicional de saida x {AVM_OUTPUT_ADJUSTMENT_FACTOR:.4f}"
        ),
        "tipo_estimativa": "90% do preço anunciado (proxy com desconto fixo)",
        "aviso": (
            "Não representa preço final de venda nem avaliação de mercado/CAIXA. "
            "Não utilizar para crédito, garantia ou decisão sem validação independente."
        ),
    }


@app.post("/predict/batch", tags=["Predição"])
def predict_batch(imoveis: List[AvmApartmentInput], modelo: Optional[str] = None):
    if not imoveis:
        raise HTTPException(422, "Informe ao menos um imóvel para estimar.")
    if len(imoveis) > 500:
        raise HTTPException(422, "O lote pode conter no máximo 500 imóveis.")
    properties = [avm_input_as_dict(imovel) for imovel in imoveis]
    direct_indexes = [
        index for index, item in enumerate(properties)
        if item.get("valor_oferta_brl") is not None
    ]
    model_indexes = [index for index in range(len(properties)) if index not in set(direct_indexes)]
    for index in model_indexes:
        _require_model_fields(properties[index])

    predictions_by_index: Dict[int, float] = {
        index: _direct_offer_target(properties[index]["valor_oferta_brl"])
        for index in direct_indexes
    }
    raw_model_predictions_by_index: Dict[int, float] = {}
    model_bundle = None
    if model_indexes:
        model_bundle = _resolve_avm_bundle(modelo)
        try:
            model_predictions = predict_discounted_offers(
                model_bundle, [properties[index] for index in model_indexes]
            )
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        for index, raw_prediction in zip(model_indexes, model_predictions):
            raw_value = float(raw_prediction)
            raw_model_predictions_by_index[index] = raw_value
            predictions_by_index[index] = round(
                raw_value * AVM_OUTPUT_ADJUSTMENT_FACTOR, 2
            )

    model_key = getattr(model_bundle, "model_type", None) if model_bundle else None
    model_entry = (
        model_bundle.report.get("available_models", {}).get(model_key, {})
        if model_bundle else {}
    )
    model_label = (
        model_entry.get("candidate", model_bundle.report["selected_model"])
        if model_bundle else "cálculo direto por oferta"
    )
    results = [
        {
            "indice": index,
            "estimativa_alvo_brl": predictions_by_index[index],
            "estimativa_modelo_bruta_brl": raw_model_predictions_by_index.get(index),
            "fator_ajuste_saida": (
                AVM_OUTPUT_ADJUSTMENT_FACTOR if index in model_indexes else 1.0
            ),
            "status": "calculado" if index in direct_indexes else "experimental",
            "metodologia": (
                "Valor de oferta informado × 0,9 (cálculo direto)"
                if index in direct_indexes
                else (
                    "AVM experimental; alvo proxy 0,90 × oferta; "
                    f"fator adicional de saida x {AVM_OUTPUT_ADJUSTMENT_FACTOR:.4f}"
                )
            ),
            "tipo_estimativa": (
                "90% do valor de oferta informado"
                if index in direct_indexes
                else "Estimativa experimental do alvo 90% do preço de oferta"
            ),
        }
        for index in range(len(imoveis))
    ]
    return {
        "status": "experimental" if model_indexes else "calculado",
        "modelo": model_label,
        "algoritmo": model_key or "fórmula",
        "alvo": (
            model_bundle.report["target_definition"] if model_bundle
            else "0,90 × valor de oferta informado"
        ),
        "quantidade": len(results),
        "fator_ajuste_saida": AVM_OUTPUT_ADJUSTMENT_FACTOR,
        "estimativas": results,
        "aviso": (
            "Não representa preço final de venda nem avaliação de mercado/CAIXA. "
            "Não utilizar para crédito, garantia ou decisão sem validação independente."
        ),
    }


@app.post(
    "/predict/workbook",
    tags=["Predição"],
    response_class=Response,
    responses={
        200: {
            "description": "Planilha Excel com a estrutura de saída do TESTE.xlsx.",
            "content": {
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {
                    "schema": {"type": "string", "format": "binary"}
                }
            },
        }
    },
)
def predict_workbook(imoveis: List[AvmApartmentInput], modelo: Optional[str] = None):
    """Estimate manually submitted properties and return the standard TESTE workbook layout."""
    result = predict_batch(imoveis, modelo)
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
    sheet.cell(1, 1, "Resultado de precificação de imóveis")
    sheet.cell(2, 1, "Estimativas geradas pela API AVM a partir dos dados enviados.")
    sheet.cell(3, 1, "Campos sem informação foram mantidos vazios; não foram presumidos como zero.")
    sheet.cell(4, 1, "A coluna AVALIAÇÃO é apenas referência e não é usada como entrada do modelo.")
    sheet.cell(5, 1, "As quatro colunas finais registram valor estimado, valor unitário, metodologia e observações.")
    sheet.cell(6, 1, "Estimativas experimentais não representam avaliação independente de mercado/CAIXA.")
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

    for index, (imovel, estimate) in enumerate(zip(imoveis, result["estimativas"]), start=1):
        item = avm_input_as_dict(imovel)
        prediction = estimate["estimativa_alvo_brl"]
        area = item.get("area_privativa_m2")
        row = header_row + index
        values = {
            1: index,
            3: item.get("valor_oferta_brl"),
            7: item.get("distrito"),
            8: item.get("cep"),
            11: item.get("quartos"),
            12: item.get("banheiros"),
            13: item.get("vagas"),
            14: item.get("elevador"),
            15: item.get("area_total_m2"),
            16: area,
            22: item.get("idade_anos"),
            23: prediction,
            24: round(prediction / area, 2) if prediction is not None and area else None,
            25: estimate.get("metodologia"),
            26: (
                "Cálculo direto: 90% da oferta informada. Não é avaliação independente de mercado/CAIXA."
                if estimate.get("status") == "calculado"
                else "Estimativa experimental do alvo de 90% do preço de oferta; não é avaliação de mercado/CAIXA."
            ),
        }
        if item.get("elevador") is None:
            values[26] += " Elevador não informado; nenhum valor foi presumido."
        for column, value in values.items():
            if value is not None:
                sheet.cell(row, column, value)
        sheet.cell(row, 23).number_format = '"R$" #,##0.00'
        sheet.cell(row, 24).number_format = '"R$" #,##0.00'
        for column in (25, 26):
            sheet.cell(row, column).alignment = Alignment(wrap_text=True, vertical="top")

    sheet.freeze_panes = "A9"
    sheet.auto_filter.ref = f"A{header_row}:Z{header_row + len(imoveis)}"
    sheet.row_dimensions[header_row].height = 34
    widths = {
        "A": 8, "B": 16, "C": 16, "D": 42, "E": 30, "F": 10,
        "G": 24, "H": 14, "I": 18, "J": 18, "K": 11, "L": 12,
        "M": 10, "N": 12, "O": 14, "P": 16, "Q": 14, "R": 18,
        "S": 18, "T": 24, "U": 20, "V": 10, "W": 20, "X": 22,
        "Y": 42, "Z": 64,
    }
    for column, width in widths.items():
        sheet.column_dimensions[column].width = width

    buffer = BytesIO()
    workbook.save(buffer)
    return Response(
        content=buffer.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="resultado_precificacao_avm.xlsx"'},
    )

@app.post("/referencia/estimativa", tags=["Experimental"])
def estimate_reference_endpoint(imovel: ReferenceEstimateInput):
    if reference_rates is None:
        raise HTTPException(
            503,
            "Referência experimental indisponível. Gere models/itbi_reference_2026.json "
            "com scripts\\experimental_reference.py.",
        )
    try:
        return estimate_reference(
            reference_rates,
            imovel.area_construida_iptu_m2,
            imovel.cep,
            imovel.codigo_padrao_iptu,
            imovel.confirmar_area_iptu,
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.post("/avaliacao/simulacao-exploratoria", tags=["Experimental"])
def estimate_caixa_exploratory_endpoint(imovel: CaixaExploratoryEstimateInput):
    if not CAIXA_VALIDATION_PATH.is_file():
        raise HTTPException(
            503,
            "A simulaÃ§Ã£o detalhada foi desativada no pacote sem a base-fonte.",
        )
    try:
        return estimate_caixa_exploratory_reference(
            imovel.area_privativa_m2,
            CAIXA_VALIDATION_PATH,
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/regioes/stats", tags=["Análise"])
def stats_regioes():
    raise HTTPException(503, MODEL_NOT_READY_REASON)


@app.get("/modelo/info", tags=["Modelo"])
def info_modelo():
    appraisal_audit = audit_evaluations_csv(EVALUATIONS_PATH)
    caixa_validation_audit = _load_caixa_validation_audit()
    backtest = reference_rates.get("temporal_backtest") if reference_rates else None
    reference_period = reference_rates.get("reference_period") if reference_rates else None
    filter_counts = reference_rates.get("filter_counts") if reference_rates else None
    avm_report = avm_bundle.report if avm_bundle is not None else {}
    selected_model_key = (
        avm_bundle.model_type if avm_bundle is not None
        else _avm_model_key(avm_report.get("selected_model"))
    )
    loaded_models = dict(avm_bundles)
    if not loaded_models and avm_bundle is not None:
        loaded_key = getattr(avm_bundle, "model_type", selected_model_key)
        if loaded_key:
            loaded_models[loaded_key] = avm_bundle
    available_model_reports = avm_report.get("available_models", {})
    selected_model_report = available_model_reports.get(selected_model_key, {})
    models_available = []
    for model_key, bundle in loaded_models.items():
        entry = available_model_reports.get(model_key, {})
        validation = entry.get("validation_metrics", {})
        models_available.append(
            {
                "id": model_key,
                "nome": {
                    "random_forest": "Random Forest",
                    "catboost": "CatBoost",
                    "xgboost": "XGBoost",
                }.get(model_key, model_key),
                "modelo": entry.get("candidate", bundle.report.get("selected_model")),
                "selecionado": model_key == selected_model_key,
                "metricas_validacao": validation,
                "metricas_teste_geografico": entry.get(
                    "independent_geographic_test_metrics",
                    avm_report.get("independent_geographic_test_metrics")
                    if model_key == selected_model_key
                    else None,
                ),
            }
        )
    return {
        "status_validacao": "suspenso",
        "habilita_predicao": False,
        "habilita_predicao_experimental_oferta": avm_bundle is not None,
        "avm_oferta_experimental": {
            "disponivel": avm_bundle is not None,
            "habilita_predicao": avm_bundle is not None,
            "homologado": False,
            "fator_ajuste_saida": AVM_OUTPUT_ADJUSTMENT_FACTOR,
            "referencia_fator_ajuste": "fator adicional configurado pelo ambiente",
            "modelo": (
                selected_model_report.get("candidate", avm_bundle.model_type)
                if avm_bundle is not None else None
            ),
            "modelos_disponiveis": models_available,
            "metricas_teste_geografico": (
                selected_model_report.get("independent_geographic_test_metrics")
                if avm_bundle is not None
                else None
            ),
            "metricas_validacao": (
                selected_model_report.get("validation_metrics")
                if avm_bundle is not None
                else None
            ),
            "metricas_baseline_teste": (
                avm_bundle.report.get("independent_test_median_baseline_metrics")
                if avm_bundle is not None
                else None
            ),
            "status_treinamento": (
                avm_bundle.report.get("status") if avm_bundle is not None else None
            ),
            "treinado_em_utc": (
                avm_bundle.report.get("generated_at_utc")
                if avm_bundle is not None
                else None
            ),
            "contagens_particoes": (
                avm_bundle.report.get("partition_counts")
                if avm_bundle is not None
                else None
            ),
            "contagens_distritos": (
                avm_bundle.report.get("partition_district_counts")
                if avm_bundle is not None
                else None
            ),
            "status_catboost": (
                avm_bundle.report.get("catboost_status")
                if avm_bundle is not None
                else None
            ),
            "status_xgboost": (
                avm_bundle.report.get("xgboost_status")
                if avm_bundle is not None
                else None
            ),
            "status_modelos": (
                avm_bundle.report.get("model_status")
                if avm_bundle is not None
                else None
            ),
            "comparacao_modelos_validacao": (
                avm_bundle.report.get("validation_metrics_by_model")
                if avm_bundle is not None
                else None
            ),
            "importancia_variaveis": (
                avm_bundle.report.get("feature_importance")
                if avm_bundle is not None
                else None
            ),
            "metricas_por_regiao": (
                avm_bundle.report.get("geographic_validation_by_region")
                if avm_bundle is not None
                else None
            ),
            "motivo_nao_homologado": (
                "O alvo é 90% da oferta, sem confirmação de preço de venda ou "
                "avaliação de mercado; a validação independente posterior permanece necessária."
            ),
        },
        "motivo_indisponibilidade": MODEL_NOT_READY_REASON,
        "metadados_legados_encontrados": metadata is not None,
        "referencia_experimental_disponivel": reference_rates is not None,
        "referencia_experimental_aprovada_para_operacao": False,
        "escopo_referencia": (
            "transacao_itbi_experimental" if reference_rates is not None else None
        ),
        "natureza_do_alvo": (
            reference_rates.get("target") if reference_rates else None
        ),
        "base_referencia": {
            "periodo": reference_period,
            "contagens": filter_counts,
            "backtest_temporal": backtest,
            "base_independente_de_avaliacoes": False,
        } if reference_rates is not None else None,
        "situacao_entregaveis": {
            "alvo_de_avaliacao_validado": False,
            "registros_candidatos_revisao_tecnica": appraisal_audit[
                "candidate_rows_for_expert_review"
            ],
            "lote_caixa_avaliacoes_candidato": caixa_validation_audit[
                "candidate_rows_for_spatial_validation"
            ],
            "validacao_temporal_caixa_possivel": caixa_validation_audit[
                "temporal_validation"
            ]["temporal_validation_possible"],
            "precos_de_oferta_auditados": False,
            "atributos_enriquecidos_com_proveniencia_validada": False,
            "infraestrutura_empresarial_comprovada": False,
            "ia_leitura_matricula_comprovada": False,
            "homologacao_caixa": False,
        },
        "auditoria_avaliacoes": appraisal_audit,
        "auditoria_validacao_caixa": caixa_validation_audit,
        "alertas": [
            "A referência ITBI estima um comparativo de transações declaradas, não uma avaliação CAIXA.",
            "A área aceita pela referência é Área Construída do cadastro IPTU; não substitui área privativa ou área total.",
            "O lote CAIXA contém rótulos candidatos para revisão e benchmark espacial, mas sua data-base da avaliação está ausente; não libera treino nem operação.",
            "Não há anúncios auditados; rótulos de avaliação exigem revisão técnica, autorização e validação independente.",
            "Os atributos preenchidos na planilha enriquecida não têm proveniência verificada por unidade/edifício.",
            "Infraestrutura empresarial e IA para leitura de matrículas precisam de evidências da empresa.",
        ],
    }


@app.get("/avaliacao/auditoria", tags=["Modelo"])
def audit_evaluation_labels():
    return audit_evaluations_csv(EVALUATIONS_PATH)


@app.get("/avaliacao/validacao-caixa", tags=["Modelo"])
def audit_caixa_validation_labels():
    return _load_caixa_validation_audit()


@app.get("/dados/catalogo", tags=["Dados"])
def data_catalog():
    if not DATA_CATALOG_PATH.is_file():
        raise HTTPException(
            503,
            "Catálogo de bases ainda não foi gerado. Execute "
            "python -B scripts\\build_data_catalog.py.",
        )
    try:
        with DATA_CATALOG_PATH.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as error:
        logger.exception("Catálogo de bases JSON inválido.")
        raise HTTPException(500, "Catálogo de bases inválido.") from error


@app.post("/relatorio", tags=["Relatório"])
def gerar_relatorio():
    raise HTTPException(503, MODEL_NOT_READY_REASON)
