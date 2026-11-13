from __future__ import annotations

import json
import hashlib
import math
import os
import platform
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
import sklearn

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "models" / "hedonic_avm"
REPORT_PATH = MODEL_DIR / "report.json"
ARTIFACT_PATH = MODEL_DIR / "hedonic_spline_ridge_v4_offer_calibrated.joblib"
MODEL_ID = "hedonic_spline_ridge_v4_offer_calibrated"
TARGET_DESCRIPTION = "Full asking/list price; calibrated on a separate offer sample; not a verified sale or CAIXA appraisal"

NUMERIC_FIELD_MAP = {
    "LATITUDE": "latitude",
    "LONGITUDE": "longitude",
    "IDADE": "idade_anos",
    "QUARTOS": "quartos",
    "BANHEIROS": "banheiros",
    "VAGAS": "vagas",
    "ELEVADOR": "elevador",
    "RENDA MEDIANA IBGE 2022 (R$)": "renda_mediana_mensal_brl",
    "RENDA MÉDIA IBGE 2022 (R$)": "renda_media_mensal_brl",
    "Área total": "area_total_m2",
    "AREA PRIV.": "area_privativa_m2",
}
CATEGORICAL_FIELD_MAP = {
    "CEP": "cep",
    "Região": "regiao",
    "Distrito": "distrito",
    "SETOR CENSITÁRIO 2022": "setor_censitario",
    "Padrão (IPTU)": "padrao_iptu",
}


def load_model() -> tuple[dict[str, Any], dict[str, Any]]:
    if not REPORT_PATH.is_file() or not ARTIFACT_PATH.is_file():
        raise RuntimeError("Artefato ou relatório do challenger hedônico ausente.")
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    if report.get("model_id") != MODEL_ID or report.get("status") != (
        "experimental_challenger_not_approved_for_operational_use"
    ):
        raise RuntimeError("Identidade ou status do artefato hedônico inválido.")
    expected = report.get("runtime_versions", {})
    actual = {
        "python": platform.python_version(),
        "scikit_learn": sklearn.__version__,
        "joblib": joblib.__version__,
    }
    for key in ("scikit_learn", "joblib"):
        if expected.get(key) != actual[key]:
            raise RuntimeError(
                f"Versão incompatível de {key}: artefato={expected.get(key)}, runtime={actual[key]}."
            )
    expected_py = ".".join(expected.get("python", "").split(".")[:2])
    actual_py = ".".join(actual["python"].split(".")[:2])
    if expected_py and expected_py != actual_py:
        raise RuntimeError(
            f"Versão incompatível de Python: artefato={expected.get('python')}, runtime={actual['python']}."
        )
    checksum_path = MODEL_DIR / "hedonic_spline_ridge_v4_offer_calibrated.sha256"
    expected_hash = checksum_path.read_text(encoding="ascii").strip().split()[0]
    actual_hash = hashlib.sha256(ARTIFACT_PATH.read_bytes()).hexdigest()
    if actual_hash != expected_hash:
        raise RuntimeError("Hash do artefato serializado não confere com o manifesto.")
    bundle = joblib.load(ARTIFACT_PATH)
    calibration_factor = float(bundle.get("offer_calibration_factor", 0))
    if not math.isfinite(calibration_factor) or calibration_factor <= 0:
        raise RuntimeError("Offer calibration factor is missing or invalid.")
    if bundle.get("model_id") != MODEL_ID:
        raise RuntimeError("O arquivo serializado não corresponde ao challenger esperado.")
    required = [*report["method"]["numeric_features"], *report["method"]["categorical_features"]]
    mapping = {**NUMERIC_FIELD_MAP, **CATEGORICAL_FIELD_MAP}
    if set(required) != set(bundle.get("feature_names", [])) or not set(required) <= set(mapping):
        raise RuntimeError("Lista de atributos ou mapeamento incompatível com o artefato.")
    if list(bundle["model"].feature_names_in_) != required:
        raise RuntimeError("As colunas do pipeline serializado não correspondem ao relatório.")
    return bundle, report


def _category(value: Any) -> str:
    return str(value).strip() if value is not None and str(value).strip() else "desconhecido"


def make_feature_frame(properties: list[dict[str, Any]], bundle: dict[str, Any]) -> pd.DataFrame:
    mapping = {**NUMERIC_FIELD_MAP, **CATEGORICAL_FIELD_MAP}
    columns = bundle["feature_names"]
    rows = []
    for item in properties:
        row: dict[str, Any] = {}
        for column in columns:
            field = mapping[column]
            value = item.get(field)
            if column == "Padrão (IPTU)":
                try:
                    number = float(value) if value is not None else None
                    value = str(int(number)) if number is not None and number >= 0 else "desconhecido"
                except (TypeError, ValueError, OverflowError):
                    value = "desconhecido"
            elif column in CATEGORICAL_FIELD_MAP:
                value = _category(value)
                if column == "CEP":
                    digits = "".join(character for character in value if character.isdigit())
                    value = digits[:5] if len(digits) >= 5 else "desconhecido"
            row[column] = value
        rows.append(row)
    return pd.DataFrame(rows, columns=columns)


def predict_many(
    bundle: dict[str, Any],
    properties: list[dict[str, Any]],
    *,
    apply_peer_alignment: bool = False,
    apply_offer_calibration: bool = False,
) -> list[float]:
    if not properties:
        return []
    if apply_peer_alignment and "peer_alignment_factor" not in bundle:
        raise ValueError("A calibração de alinhamento com pares não está instalada.")
    frame = make_feature_frame(properties, bundle)
    log_predictions = bundle["model"].predict(frame)
    smearing = float(bundle["smearing_factor"])
    offer_factor = float(bundle["offer_calibration_factor"]) if apply_offer_calibration else 1.0
    peer_factor = float(bundle.get("peer_alignment_factor", 1.0)) if apply_peer_alignment else 1.0
    results = []
    for log_value in log_predictions:
        prediction = math.exp(max(-30.0, min(30.0, float(log_value)))) * smearing * offer_factor * peer_factor
        if not math.isfinite(prediction) or prediction <= 0:
            raise ValueError("O modelo retornou uma estimativa inválida.")
        results.append(round(prediction, 2))
    return results
