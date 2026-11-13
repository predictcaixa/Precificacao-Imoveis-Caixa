"""Load the experimental offer AVM and predict its discounted-offer target."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .train_offer_avm import (
    BASE_DIR,
    FEATURE_ALLOWLIST,
    build_feature_row,
)


@dataclass
class AvmModelBundle:
    model: Any
    report: dict[str, Any]
    model_type: str


def build_api_feature_row(property_data: dict[str, Any]) -> dict[str, Any]:
    region = property_data.get("regiao")
    region = region.strip() if isinstance(region, str) else ""
    row = {
        "LATITUDE": property_data.get("latitude"),
        "LONGITUDE": property_data.get("longitude"),
        "IDADE": property_data.get("idade_anos"),
        "QUARTOS": property_data.get("quartos"),
        "BANHEIROS": property_data.get("banheiros"),
        "VAGAS": property_data.get("vagas"),
        "ELEVADOR": property_data.get("elevador"),
        "RENDA MEDIANA IBGE 2022 (R$)": property_data.get(
            "renda_mediana_mensal_brl"
        ),
        "RENDA MÉDIA IBGE 2022 (R$)": property_data.get(
            "renda_media_mensal_brl"
        ),
        "Área total": property_data.get("area_total_m2"),
        "AREA PRIV.": property_data.get("area_privativa_m2"),
        "CEP": property_data.get("cep"),
        "Região": region or "desconhecido",
        "Distrito": property_data.get("distrito") or "desconhecido",
        "SETOR CENSITÁRIO 2022": property_data.get("setor_censitario")
        or "desconhecido",
        "Padrão (IPTU)": property_data.get("padrao_iptu"),
    }
    return build_feature_row(row)


def _read_avm_report(report_path: Path) -> dict[str, Any]:
    if not report_path.is_file():
        raise FileNotFoundError(f"Relatório do AVM não encontrado: {report_path}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise ValueError("O relatório do AVM deve ser um objeto JSON.")
    if report.get("status") != "experimental_not_operationally_approved":
        raise ValueError("Status inesperado no relatório do AVM.")
    feature_names = report.get("feature_columns")
    if (
        not isinstance(feature_names, list)
        or not feature_names
        or not set(feature_names) <= set(FEATURE_ALLOWLIST)
    ):
        raise ValueError("O relatório contém features inválidas ou não permitidas.")

    return report


def _load_model_bundle(
    report: dict[str, Any],
    model_key: str,
    model_entry: dict[str, Any],
) -> AvmModelBundle:
    model_name = model_entry.get("candidate") or model_entry.get("name") or model_key
    artifact_value = model_entry.get("model_file")
    if artifact_value is None and model_key == _model_key_for_name(
        report.get("selected_model")
    ):
        artifact_value = report.get("model_file")
    if not isinstance(artifact_value, str) or not artifact_value.strip():
        raise ValueError(f"O relatório não informa o artefato do modelo {model_key}.")
    rel_path = Path(*artifact_value.replace("\\", "/").strip("/").split("/"))
    artifact_path = (BASE_DIR / rel_path).resolve()
    if not artifact_path.is_relative_to(BASE_DIR.resolve()):
        raise ValueError("O caminho do artefato do AVM está fora do projeto.")

    if model_key == "catboost" or model_name.startswith("catboost"):
        try:
            from catboost import CatBoostRegressor
        except ImportError as error:
            raise RuntimeError(
                "O modelo requer CatBoost. Instale o artefato em Python compatível "
                "com CatBoost antes de iniciar a API."
            ) from error
        model = CatBoostRegressor()
        model.load_model(str(artifact_path))
        model_type = "catboost"
    elif model_key == "xgboost" or model_name.startswith("xgboost"):
        try:
            import xgboost
            import joblib
        except ImportError as error:
            raise RuntimeError(
                "O modelo requer XGBoost e joblib. Instale as dependências "
                "em um Python compatível antes de iniciar a API."
            ) from error
        model = joblib.load(artifact_path)
        model_type = "xgboost"
    elif model_key == "random_forest" or model_name == "random_forest":
        try:
            import joblib
        except ImportError as error:
            raise RuntimeError(
                "O modelo Random Forest requer joblib/scikit-learn."
            ) from error
        model = joblib.load(artifact_path)
        model_type = "random_forest"
    else:
        raise ValueError(f"Tipo de modelo não suportado: {model_key}")
    return AvmModelBundle(model=model, report=report, model_type=model_type)


def load_avm_model(report_path: Path, model_key: str | None = None) -> AvmModelBundle:
    report = _read_avm_report(report_path)
    key = model_key or _model_key_for_name(report.get("selected_model"))
    if key is None:
        raise ValueError("O relatório não informa um algoritmo selecionado válido.")
    available = report.get("available_models", {})
    if not isinstance(available, dict):
        raise ValueError("A lista de modelos disponíveis no relatório é inválida.")
    entry = available.get(key, {})
    if not isinstance(entry, dict):
        raise ValueError(f"Metadados do modelo {key} são inválidos.")
    return _load_model_bundle(report, key, entry)


def load_avm_models(report_path: Path) -> dict[str, AvmModelBundle]:
    report = _read_avm_report(report_path)
    available = report.get("available_models")
    if not isinstance(available, dict):
        selected = _model_key_for_name(report.get("selected_model"))
        if selected is None:
            raise ValueError("O relatório não informa um algoritmo selecionado válido.")
        return {selected: load_avm_model(report_path, selected)}

    bundles = {}
    for key in ("random_forest", "catboost", "xgboost"):
        entry = available.get(key)
        if not isinstance(entry, dict):
            continue
        if entry.get("status") != "trained":
            continue
        bundles[key] = _load_model_bundle(report, key, entry)
    if not bundles:
        raise ValueError("O relatório não contém nenhum modelo treinado disponível.")
    return bundles


def _model_key_for_name(model_name: object) -> str | None:
    if not isinstance(model_name, str):
        return None
    if model_name.startswith("catboost"):
        return "catboost"
    if model_name.startswith("xgboost"):
        return "xgboost"
    if model_name == "random_forest":
        return "random_forest"
    return None


def predict_discounted_offer(
    bundle: AvmModelBundle, property_data: dict[str, Any]
) -> float:
    return predict_discounted_offers(bundle, [property_data])[0]


def predict_discounted_offers(
    bundle: AvmModelBundle, properties: list[dict[str, Any]]
) -> list[float]:
    if not properties:
        raise ValueError("Informe ao menos um imóvel para estimar.")
    import pandas as pd

    feature_names = bundle.report["feature_columns"]
    feature_rows = [build_api_feature_row(item) for item in properties]
    model_input = pd.DataFrame(
        [
            {name: feature_row[name] for name in feature_names}
            for feature_row in feature_rows
        ],
        columns=feature_names,
    )
    predictions = bundle.model.predict(model_input)
    if len(predictions) != len(properties):
        raise ValueError("O modelo retornou quantidade inesperada de previsões.")
    results = []
    for prediction in predictions:
        value = float(prediction)
        if not math.isfinite(value):
            raise ValueError("O modelo retornou uma previsão não finita.")
        if value > 709:
            raise ValueError("O modelo retornou uma previsão fora da faixa numérica.")
        discounted_offer = math.expm1(value)
        if not math.isfinite(discounted_offer) or discounted_offer < 0:
            raise ValueError("O modelo retornou um valor estimado inválido.")
        results.append(round(discounted_offer, 2))
    return results
