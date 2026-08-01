"""
main.py — API REST de Precificação de Imóveis
==============================================
Endpoints:
  GET  /                         → health check
  POST /predict                  → prediz preço de um imóvel
  POST /predict/batch            → prediz lista de imóveis
  GET  /regioes/stats            → estatísticas por região
  GET  /modelo/info              → métricas e metadados do modelo
  POST /relatorio                → gera relatório PDF/JSON
  GET  /docs                     → Swagger UI automático

Execução:
  uvicorn app.main:app --reload --port 8000
"""

import os
import json
import pickle
import logging
from datetime import datetime
from typing import List, Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ─── PATHS ──────────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(BASE_DIR, "models")
DATA_PATH  = os.path.join(BASE_DIR, "data", "imoveis_joinville.csv")

# ─── FASTAPI ─────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="ImóvelML API",
    description="API de precificação de imóveis com Machine Learning — Joinville, SC",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # Em produção: defina domínios específicos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── CARREGAR MODELO E METADADOS ─────────────────────────────────────────────────
modelo      = None
metadata    = None
df_dados    = None

REGIOES_VALIDAS = ["centro", "america", "anita", "norte", "sul"]

NOMES_REGIOES = {
    "centro":  "Centro",
    "america": "América",
    "anita":   "Anita Garibaldi",
    "norte":   "Zona Norte",
    "sul":     "Zona Sul",
}


@app.on_event("startup")
async def carregar_recursos():
    global modelo, metadata, df_dados
    try:
        meta_path = os.path.join(MODELS_DIR, "metadata.json")
        with open(meta_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        modelo_principal = metadata.get("modelo_principal", "random_forest")
        pkl_path = os.path.join(MODELS_DIR, f"modelo_{modelo_principal}.pkl")
        with open(pkl_path, "rb") as f:
            modelo = pickle.load(f)

        df_dados = pd.read_csv(DATA_PATH)
        logger.info(f"Modelo '{modelo_principal}' carregado. Dataset: {len(df_dados)} registros.")
    except FileNotFoundError:
        logger.warning("Modelos não encontrados. Execute train_model.py primeiro.")


# ─── SCHEMAS ────────────────────────────────────────────────────────────────────

class ImovelInput(BaseModel):
    regiao:     str   = Field(..., description="Região do imóvel", example="centro")
    area:       float = Field(..., ge=20, le=1000, description="Área em m²", example=85)
    quartos:    int   = Field(..., ge=1, le=10,   description="Número de quartos", example=3)
    banheiros:  int   = Field(..., ge=1, le=10,   description="Número de banheiros", example=2)
    vagas:      int   = Field(..., ge=0, le=10,   description="Vagas de garagem", example=1)
    idade:      int   = Field(..., ge=0, le=60,   description="Idade do imóvel em anos", example=5)
    suite:      int   = Field(0,  ge=0, le=5,    description="Suítes")
    sacada:     int   = Field(0,  ge=0, le=3,    description="Sacadas/varandas")
    piscina:    int   = Field(0,  ge=0, le=1,    description="Piscina (0=não, 1=sim)")

    @validator("regiao")
    def validar_regiao(cls, v):
        if v.lower() not in REGIOES_VALIDAS:
            raise ValueError(f"Região inválida. Use: {REGIOES_VALIDAS}")
        return v.lower()


class ImovelOutput(BaseModel):
    preco_estimado:   float
    intervalo_minimo: float
    intervalo_maximo: float
    preco_por_m2:     float
    regiao_nome:      str
    confianca:        str
    comparaveis:      List[dict]


class RelatorioInput(BaseModel):
    regioes:    Optional[List[str]] = None   # None = todas
    quartos_min: int = 1
    quartos_max: int = 5
    area_min:    float = 30
    area_max:    float = 500
    formato:     str = "json"               # "json" | "resumo"


# ─── FUNÇÃO DE PREDIÇÃO ──────────────────────────────────────────────────────────

def construir_features(imovel: ImovelInput) -> pd.DataFrame:
    """
    Replica exatamente a engenharia de features do train_model.py
    """
    num_cols = {
        "area":      imovel.area,
        "quartos":   imovel.quartos,
        "banheiros": imovel.banheiros,
        "vagas":     imovel.vagas,
        "idade":     imovel.idade,
        "suite":     imovel.suite,
        "sacada":    imovel.sacada,
        "piscina":   imovel.piscina,
        "area_por_quarto": imovel.area / max(imovel.quartos, 1),
        "luxo_score": imovel.suite + imovel.sacada + imovel.piscina * 2,
    }

    # Dummy encoding da região (mesmo esquema do treinamento)
    for r in REGIOES_VALIDAS:
        num_cols[f"regiao_{r}"] = 1 if imovel.regiao == r else 0

    df = pd.DataFrame([num_cols])

    # Garantir ordem exata das features
    if metadata:
        df = df.reindex(columns=metadata["feature_names"], fill_value=0)

    return df


def buscar_comparaveis(imovel: ImovelInput, preco: float, n: int = 3) -> List[dict]:
    if df_dados is None:
        return []
    filtro = df_dados[df_dados["regiao"] == imovel.regiao].copy()
    filtro["dist_preco"] = abs(filtro["preco"] - preco)
    top = filtro.nsmallest(n, "dist_preco")
    return top[["area", "quartos", "banheiros", "vagas", "idade", "preco"]].to_dict(orient="records")


# ─── ENDPOINTS ──────────────────────────────────────────────────────────────────

@app.get("/", tags=["Status"])
def health():
    return {
        "status": "online",
        "modelo_carregado": modelo is not None,
        "versao": "1.0.0",
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/predict", response_model=ImovelOutput, tags=["Predição"])
def predict(imovel: ImovelInput):
    if modelo is None:
        raise HTTPException(503, "Modelo não carregado. Execute train_model.py.")

    X = construir_features(imovel)
    preco = float(modelo.predict(X)[0])

    # Intervalo de confiança: ±10% (em produção: use quantile regression)
    margem = preco * 0.10
    preco_min = max(preco - margem, 0)
    preco_max = preco + margem

    # Confiança baseada nas métricas do modelo
    r2 = metadata["metricas"]["random_forest"]["r2"] if metadata else 0.0
    confianca = "Alta" if r2 > 0.90 else "Média" if r2 > 0.75 else "Baixa"

    return ImovelOutput(
        preco_estimado=round(preco, 2),
        intervalo_minimo=round(preco_min, 2),
        intervalo_maximo=round(preco_max, 2),
        preco_por_m2=round(preco / imovel.area, 2),
        regiao_nome=NOMES_REGIOES[imovel.regiao],
        confianca=confianca,
        comparaveis=buscar_comparaveis(imovel, preco),
    )


@app.post("/predict/batch", tags=["Predição"])
def predict_batch(imoveis: List[ImovelInput]):
    if modelo is None:
        raise HTTPException(503, "Modelo não carregado.")
    if len(imoveis) > 100:
        raise HTTPException(400, "Máximo 100 imóveis por requisição.")

    resultados = []
    for i, imovel in enumerate(imoveis):
        X = construir_features(imovel)
        preco = float(modelo.predict(X)[0])
        margem = preco * 0.10
        resultados.append({
            "index": i,
            "regiao": imovel.regiao,
            "area": imovel.area,
            "preco_estimado": round(preco, 2),
            "intervalo_minimo": round(preco - margem, 2),
            "intervalo_maximo": round(preco + margem, 2),
            "preco_por_m2": round(preco / imovel.area, 2),
        })

    return {"total": len(resultados), "predicoes": resultados}


@app.get("/regioes/stats", tags=["Análise"])
def stats_regioes():
    if df_dados is None:
        raise HTTPException(503, "Dataset não carregado.")

    stats = []
    for regiao in REGIOES_VALIDAS:
        sub = df_dados[df_dados["regiao"] == regiao]
        if sub.empty:
            continue
        stats.append({
            "regiao":        regiao,
            "nome":          NOMES_REGIOES[regiao],
            "total_imoveis": len(sub),
            "preco_medio":   round(sub["preco"].mean(), 2),
            "preco_mediano": round(sub["preco"].median(), 2),
            "preco_minimo":  round(sub["preco"].min(), 2),
            "preco_maximo":  round(sub["preco"].max(), 2),
            "preco_m2_medio":round((sub["preco"] / sub["area"]).mean(), 2),
            "area_media":    round(sub["area"].mean(), 2),
            "quartos_media": round(sub["quartos"].mean(), 2),
        })

    return {"regioes": stats, "total_dataset": len(df_dados)}


@app.get("/modelo/info", tags=["Modelo"])
def info_modelo():
    if metadata is None:
        raise HTTPException(503, "Metadados não disponíveis.")
    return {
        "modelo_principal": metadata.get("modelo_principal"),
        "features":         metadata.get("feature_names"),
        "metricas":         metadata.get("metricas"),
        "importancias":     metadata.get("importancias", {}),
    }


@app.post("/relatorio", tags=["Relatório"])
def gerar_relatorio(params: RelatorioInput):
    """
    Gera relatório de predições para um conjunto de perfis de imóveis por região.
    Retorna JSON estruturado pronto para exportar ou renderizar no frontend.
    """
    if modelo is None:
        raise HTTPException(503, "Modelo não carregado.")

    regioes_alvo = params.regioes or REGIOES_VALIDAS
    regioes_alvo = [r for r in regioes_alvo if r in REGIOES_VALIDAS]

    # Perfis padrão para o relatório
    perfis = [
        {"desc": "Compacto (1 quarto)",  "quartos": 1, "banheiros": 1, "vagas": 0, "area": 45,  "idade": 5,  "suite": 0, "sacada": 0, "piscina": 0},
        {"desc": "Padrão (2 quartos)",   "quartos": 2, "banheiros": 2, "vagas": 1, "area": 70,  "idade": 8,  "suite": 1, "sacada": 0, "piscina": 0},
        {"desc": "Familiar (3 quartos)", "quartos": 3, "banheiros": 2, "vagas": 2, "area": 95,  "idade": 5,  "suite": 1, "sacada": 1, "piscina": 0},
        {"desc": "Alto padrão (4 qtos)", "quartos": 4, "banheiros": 3, "vagas": 2, "area": 135, "idade": 3,  "suite": 2, "sacada": 1, "piscina": 0},
        {"desc": "Luxo (5 quartos)",     "quartos": 5, "banheiros": 4, "vagas": 3, "area": 200, "idade": 2,  "suite": 3, "sacada": 2, "piscina": 1},
    ]

    tabela = []
    for regiao in regioes_alvo:
        for perfil in perfis:
            if not (params.quartos_min <= perfil["quartos"] <= params.quartos_max):
                continue
            if not (params.area_min <= perfil["area"] <= params.area_max):
                continue

            inp = ImovelInput(regiao=regiao, **{k: v for k, v in perfil.items() if k != "desc"})
            X = construir_features(inp)
            preco = float(modelo.predict(X)[0])
            margem = preco * 0.10
            tabela.append({
                "regiao":          regiao,
                "regiao_nome":     NOMES_REGIOES[regiao],
                "perfil":          perfil["desc"],
                "area":            perfil["area"],
                "quartos":         perfil["quartos"],
                "vagas":           perfil["vagas"],
                "preco_estimado":  round(preco, 2),
                "preco_minimo":    round(preco - margem, 2),
                "preco_maximo":    round(preco + margem, 2),
                "preco_por_m2":    round(preco / perfil["area"], 2),
            })

    # Sumário por região
    df_rel = pd.DataFrame(tabela)
    sumario = []
    for regiao in regioes_alvo:
        sub = df_rel[df_rel["regiao"] == regiao]
        if sub.empty:
            continue
        sumario.append({
            "regiao":       regiao,
            "nome":         NOMES_REGIOES[regiao],
            "preco_min":    round(sub["preco_estimado"].min(), 2),
            "preco_max":    round(sub["preco_estimado"].max(), 2),
            "preco_medio":  round(sub["preco_estimado"].mean(), 2),
            "m2_medio":     round(sub["preco_por_m2"].mean(), 2),
        })

    return {
        "gerado_em":   datetime.now().isoformat(),
        "total_linhas": len(tabela),
        "sumario_regioes": sumario,
        "tabela_detalhada": tabela,
    }
