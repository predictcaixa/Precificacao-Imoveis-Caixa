"""Audit CAIXA appraisal labels and run leakage-safe spatial baseline validation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = BASE_DIR / "scripts" / "dados" / "caixa_sp_validacao.csv"
DEFAULT_OUTPUT = BASE_DIR / "scripts" / "dados" / "caixa_sp_validacao_audit.json"
EXPECTED_COLUMNS = {
    "n_do_imovel",
    "cidade",
    "bairro",
    "endereco",
    "tipo",
    "area_ref_m2",
    "area_tipo",
    "quartos",
    "vagas",
    "valor_avaliacao_brl",
    "avaliacao_brl_m2",
    "preco_venda_brl",
    "desconto_pct",
    "modalidade_de_venda",
    "link_de_acesso",
    "fonte",
    "natureza_do_valor",
    "data_coleta",
    "avaliacao_data",
    "sql_iptu",
}
MIN_AREA_M2 = 10.0
MAX_AREA_M2 = 2000.0
SPATIAL_FOLDS = 5


def _read_rows(path: Path) -> tuple[list[dict[str, str]], list[str], str]:
    if not path.is_file():
        raise FileNotFoundError(f"CSV CAIXA não encontrado: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(8192)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error as error:
            raise ValueError("Não foi possível identificar o delimitador do CSV CAIXA.") from error
        reader = csv.DictReader(handle, dialect=dialect)
        rows = [
            {key: (value or "").strip() for key, value in raw.items() if key}
            for raw in reader
            if raw and any((value or "").strip() for value in raw.values())
        ]
        return rows, reader.fieldnames or [], dialect.delimiter


def _number(value: str | None) -> float | None:
    text = (value or "").strip()
    if not text:
        return None
    if "," in text and "." in text:
        decimal_separator = "," if text.rfind(",") > text.rfind(".") else "."
        grouping_separator = "." if decimal_separator == "," else ","
        text = text.replace(grouping_separator, "").replace(decimal_separator, ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        parsed = float(text)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def estimate_caixa_exploratory_reference(
    area_m2: float,
    input_path: Path = DEFAULT_INPUT,
) -> dict[str, Any]:
    if not math.isfinite(area_m2) or not MIN_AREA_M2 <= area_m2 <= MAX_AREA_M2:
        raise ValueError(
            f"A área privativa deve estar entre {MIN_AREA_M2:g} e {MAX_AREA_M2:g} m²."
        )

    rows, fields, _ = _read_rows(input_path)
    missing_columns = sorted(EXPECTED_COLUMNS - set(fields))
    if missing_columns:
        raise ValueError(
            "CSV CAIXA sem colunas necessárias: " + ", ".join(missing_columns)
        )

    rates: list[float] = []
    for row in rows:
        property_type = row["tipo"].strip().casefold()
        city = row["cidade"].strip().casefold()
        nature = row["natureza_do_valor"].strip().casefold()
        source = row["fonte"].strip().casefold()
        area_type = row["area_tipo"].strip().casefold()
        source_area = _number(row["area_ref_m2"])
        target = _number(row["valor_avaliacao_brl"])
        if (
            property_type in {"apartamento", "apartment"}
            and city in {"sao paulo", "são paulo"}
            and nature == "avaliacao_caixa_imovel_retomado"
            and source == "caixa_lista_imoveis_oficial"
            and area_type in {"privativa", "private"}
            and source_area is not None
            and MIN_AREA_M2 <= source_area <= MAX_AREA_M2
            and target is not None
            and target > 0
        ):
            rates.append(target / source_area)

    if not rates:
        raise ValueError("Não há registros CAIXA elegíveis para a referência exploratória.")

    rates.sort()
    rate = statistics.median(rates)
    p10_rate = rates[int((len(rates) - 1) * 0.1)]
    p90_rate = rates[int((len(rates) - 1) * 0.9)]
    neighborhood_count = len(
        {
            row["bairro"].strip().casefold()
            for row in rows
            if row["bairro"].strip()
            and row["tipo"].strip().casefold() in {"apartamento", "apartment"}
            and row["cidade"].strip().casefold() in {"sao paulo", "são paulo"}
            and row["natureza_do_valor"].strip().casefold()
            == "avaliacao_caixa_imovel_retomado"
            and row["fonte"].strip().casefold() == "caixa_lista_imoveis_oficial"
            and row["area_tipo"].strip().casefold() in {"privativa", "private"}
            and (source_area := _number(row["area_ref_m2"])) is not None
            and MIN_AREA_M2 <= source_area <= MAX_AREA_M2
            and (source_target := _number(row["valor_avaliacao_brl"])) is not None
            and source_target > 0
        }
    )
    return {
        "status": "exploratory_simulation_not_operational",
        "target": "valor_avaliacao_brl do lote CAIXA de imóveis retomados",
        "input_area_m2": round(area_m2, 2),
        "area_definition": "Área privativa informada; não converter de área construída IPTU.",
        "estimate_brl": round(rate * area_m2, 2),
        "rate_median_brl_per_m2": round(rate, 2),
        "observed_reference_range_brl": {
            "p10": round(p10_rate * area_m2, 2),
            "p90": round(p90_rate * area_m2, 2),
            "method": "floor((n-1)*p) order statistic of candidate appraisal rates",
        },
        "support": {
            "candidate_records": len(rates),
            "neighborhoods": neighborhood_count,
            "source": "CAIXA listed repossessed properties, single collection snapshot",
        },
        "source_collection_dates": sorted(
            {
                row["data_coleta"][:10]
                for row in rows
                if _valid_date(row["data_coleta"])
            }
        ),
        "appraisal_date_coverage_percent": 0.0,
        "operational_prediction_enabled": False,
        "disclaimer": (
            "Simulação matemática baseada na mediana e nos percentis do valor de "
            "avaliação por m² do lote CAIXA. Não é uma avaliação profissional, "
            "preço de mercado validado, recomendação de crédito nem resultado "
            "aprovado para decisão ou operação. A data-base dos valores está "
            "ausente; a amostra é de imóveis retomados e não representa todo o mercado."
        ),
    }


def _valid_date(value: str | None) -> bool:
    if not value:
        return False
    try:
        date.fromisoformat(value[:10])
    except ValueError:
        return False
    return True


def _median(values: list[float]) -> float:
    if not values:
        raise ValueError("Não há valores para calcular a mediana.")
    return statistics.median(values)


def _metrics(actuals: list[float], predictions: list[float]) -> dict[str, float]:
    if not actuals or len(actuals) != len(predictions):
        raise ValueError("A validação requer alvos e previsões pareados.")
    errors = [abs(actual - prediction) for actual, prediction in zip(actuals, predictions)]
    apes = [error / actual for error, actual in zip(errors, actuals) if actual > 0]
    ordered_apes = sorted(apes)
    mean_actual = statistics.mean(actuals)
    total_variance = sum((actual - mean_actual) ** 2 for actual in actuals)
    residual_sum_squares = sum(
        (actual - prediction) ** 2
        for actual, prediction in zip(actuals, predictions)
    )
    smape_values = [
        200 * error / (abs(actual) + abs(prediction))
        for error, actual, prediction in zip(errors, actuals, predictions)
        if abs(actual) + abs(prediction) > 0
    ]

    def percentile(values: list[float], probability: float) -> float:
        return values[int((len(values) - 1) * probability)]

    return {
        "mae_brl": round(statistics.mean(errors), 2),
        "rmse_brl": round(math.sqrt(statistics.mean(error**2 for error in errors)), 2),
        "median_absolute_percentage_error_percent": round(
            _median(apes) * 100, 4
        ),
        "p90_absolute_percentage_error_percent": round(
            percentile(ordered_apes, 0.9) * 100, 4
        ),
        "wape_percent": round(sum(errors) / sum(actuals) * 100, 4),
        "smape_percent": round(statistics.mean(smape_values), 4),
        "r2": round(
            1 - residual_sum_squares / total_variance if total_variance else 0,
            6,
        ),
    }


def _spatial_fold_indices(records: list[dict[str, Any]]) -> list[int]:
    group_rows: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(records):
        group_rows[row["neighborhood"]].append(index)
    if len(group_rows) < SPATIAL_FOLDS:
        raise ValueError(
            f"A validação espacial exige ao menos {SPATIAL_FOLDS} bairros distintos."
        )

    fold_sizes = [0] * SPATIAL_FOLDS
    fold_for_group: dict[str, int] = {}
    ordered_groups = sorted(group_rows, key=lambda group: (-len(group_rows[group]), group))
    for group in ordered_groups:
        fold = min(range(SPATIAL_FOLDS), key=lambda candidate: fold_sizes[candidate])
        fold_for_group[group] = fold
        fold_sizes[fold] += len(group_rows[group])
    return [
        fold_for_group[row["neighborhood"]]
        for row in records
    ]


def _spatial_baseline_validation(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    fold_ids = _spatial_fold_indices(records)
    actuals = [row["target"] for row in records]
    predictions = {
        "training_citywide_median": [0.0] * len(records),
        "training_median_per_m2_times_private_area": [0.0] * len(records),
    }
    fold_summaries = []
    for fold in range(SPATIAL_FOLDS):
        test_indices = [i for i, fold_id in enumerate(fold_ids) if fold_id == fold]
        train_indices = [i for i, fold_id in enumerate(fold_ids) if fold_id != fold]
        if not train_indices or not test_indices:
            raise ValueError("A divisão espacial gerou uma partição vazia.")
        training_values = [actuals[i] for i in train_indices]
        training_rates = [
            records[i]["target"] / records[i]["area_m2"] for i in train_indices
        ]
        global_median = _median(training_values)
        rate_median = _median(training_rates)
        for index in test_indices:
            predictions["training_citywide_median"][index] = global_median
            predictions["training_median_per_m2_times_private_area"][index] = (
                rate_median * records[index]["area_m2"]
            )
        fold_summaries.append(
            {
                "fold": fold + 1,
                "training_rows": len(train_indices),
                "test_rows": len(test_indices),
                "training_neighborhoods": len(
                    {records[i]["neighborhood"] for i in train_indices}
                ),
                "test_neighborhoods": len(
                    {records[i]["neighborhood"] for i in test_indices}
                ),
                "neighborhood_overlap": False,
            }
        )

    return {
        "method": (
            "5-fold spatial cross-validation grouped by neighborhood; each "
            "neighborhood appears in test in one fold only."
        ),
        "rows_evaluated": len(records),
        "neighborhoods_evaluated": len(
            {row["neighborhood"] for row in records}
        ),
        "features_used": ["area_ref_m2 (private area)"],
        "excluded_as_predictors": [
            "valor_avaliacao_brl_m2 (derived from target and area)",
            "preco_venda_brl (auction/listing price, not appraisal target)",
            "desconto_pct (may be derived from appraisal and price)",
            "n_do_imovel",
            "endereco",
            "link_de_acesso",
            "sql_iptu",
        ],
        "estimators": {
            name: {
                "description": description,
                "out_of_fold_metrics": _metrics(actuals, prediction),
            }
            for name, description, prediction in (
                (
                    "training_citywide_median",
                    "Mediana municipal do valor de avaliação no conjunto de treino.",
                    predictions["training_citywide_median"],
                ),
                (
                    "training_median_per_m2_times_private_area",
                    "Mediana de avaliação por m² no treino multiplicada pela área privativa.",
                    predictions["training_median_per_m2_times_private_area"],
                ),
            )
        },
        "folds": fold_summaries,
        "temporal_validation_possible": False,
    }


def _area_band(area: float) -> str:
    if area <= 40:
        return "le_40"
    if area <= 60:
        return "40_60"
    if area <= 80:
        return "60_80"
    if area <= 120:
        return "80_120"
    return "gt_120"


def _feature_incremental_validation(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    complete_indices = [
        index
        for index, row in enumerate(records)
        if row["bedrooms"] is not None and row["parking"] is not None
    ]
    coverage = len(complete_indices) / len(records) * 100 if records else 0
    if len(complete_indices) < 30:
        return {
            "status": "insufficient_complete_cases",
            "rows_with_area_bedrooms_and_parking": len(complete_indices),
            "complete_case_coverage_percent": round(coverage, 2),
            "minimum_rows_required": 30,
            "result": None,
        }

    fold_ids = _spatial_fold_indices(records)
    baseline_actuals: list[float] = []
    baseline_predictions: list[float] = []
    enriched_actuals: list[float] = []
    enriched_predictions: list[float] = []
    minimum_group_size = 5
    fallback_rows = 0

    for fold in range(SPATIAL_FOLDS):
        train_indices = [
            index for index, fold_id in enumerate(fold_ids) if fold_id != fold
        ]
        test_indices = [
            index
            for index in complete_indices
            if fold_ids[index] == fold
        ]
        complete_train = [
            index
            for index in train_indices
            if records[index]["bedrooms"] is not None
            and records[index]["parking"] is not None
        ]
        training_rates = [
            records[index]["target"] / records[index]["area_m2"]
            for index in train_indices
        ]
        area_rate = _median(training_rates)
        group_targets: dict[tuple[str, float, float], list[float]] = defaultdict(list)
        for index in complete_train:
            row = records[index]
            key = (
                _area_band(row["area_m2"]),
                row["bedrooms"],
                row["parking"],
            )
            group_targets[key].append(row["target"])
        group_medians = {
            key: _median(values)
            for key, values in group_targets.items()
            if len(values) >= minimum_group_size
        }

        for index in test_indices:
            row = records[index]
            target = row["target"]
            baseline_actuals.append(target)
            baseline_predictions.append(area_rate * row["area_m2"])
            key = (
                _area_band(row["area_m2"]),
                row["bedrooms"],
                row["parking"],
            )
            prediction = group_medians.get(key)
            if prediction is None:
                prediction = area_rate * row["area_m2"]
                fallback_rows += 1
            enriched_actuals.append(target)
            enriched_predictions.append(prediction)

    return {
        "status": "exploratory_spatial_feature_ablation",
        "rows_with_area_bedrooms_and_parking": len(complete_indices),
        "complete_case_coverage_percent": round(coverage, 2),
        "features_tested": [
            "area_ref_m2 (private area)",
            "quartos (source field, unit-level evidence unverified)",
            "vagas (source field, unit-level evidence unverified)",
        ],
        "validation": "same 5-fold neighborhood split and same complete-case test rows",
        "minimum_group_size": minimum_group_size,
        "enriched_group_prediction_fallback_rows": fallback_rows,
        "baseline_area_rate": _metrics(baseline_actuals, baseline_predictions),
        "area_bedrooms_parking_groups": _metrics(
            enriched_actuals, enriched_predictions
        ),
        "promotion_decision": "not_evaluated_or_approved",
        "caveat": (
            "Benchmark exploratório na mesma fonte; quartos/vagas precisam de "
            "evidência por unidade, e a amostra não é validação independente."
        ),
    }


def _temporal_holdout_validation(records: list[dict[str, Any]]) -> dict[str, Any]:
    dated_records = [row for row in records if row["appraisal_date"] is not None]
    distinct_dates = sorted({row["appraisal_date"] for row in dated_records})
    result: dict[str, Any] = {
        "date_field": "avaliacao_data",
        "date_field_semantics": "data-base da avaliação, não data de coleta/anúncio",
        "dated_candidate_rows": len(dated_records),
        "distinct_appraisal_dates": len(distinct_dates),
        "temporal_validation_possible": False,
        "status": "blocked_missing_appraisal_date",
        "reason": (
            "A data-base da avaliação é necessária; data_coleta não a substitui."
        ),
    }
    if len(distinct_dates) < 2:
        return result

    test_start_index = min(
        max(1, int(len(distinct_dates) * 0.8)),
        len(distinct_dates) - 1,
    )
    test_start = distinct_dates[test_start_index]
    train_records = [row for row in dated_records if row["appraisal_date"] < test_start]
    test_records = [row for row in dated_records if row["appraisal_date"] >= test_start]
    train_ids = {row["property_key"] for row in train_records if row["property_key"]}
    test_records = [
        row
        for row in test_records
        if not row["property_key"] or row["property_key"] not in train_ids
    ]
    if not train_records or not test_records:
        result.update(
            status="blocked_empty_chronological_partition",
            reason="A divisão cronológica não produziu treino e teste utilizáveis.",
        )
        return result

    rate = _median(
        [row["target"] / row["area_m2"] for row in train_records]
    )
    result.update(
        status="exploratory_temporal_holdout",
        reason=None,
        temporal_validation_possible=True,
        training_rows=len(train_records),
        test_rows=len(test_records),
        training_end_date=max(row["appraisal_date"] for row in train_records).isoformat(),
        test_start_date=test_start.isoformat(),
        test_end_date=max(row["appraisal_date"] for row in test_records).isoformat(),
        repeated_property_rows_excluded=len(dated_records)
        - len(train_records)
        - len(test_records),
        estimator="training median appraisal rate per m² × private area",
        metrics=_metrics(
            [row["target"] for row in test_records],
            [rate * row["area_m2"] for row in test_records],
        ),
        caveat=(
            "Holdout temporal da mesma fonte; não substitui validação independente "
            "nem revisão dos rótulos."
        ),
    )
    return result


def audit_dataset(input_path: Path = DEFAULT_INPUT) -> dict[str, Any]:
    rows, fields, delimiter = _read_rows(input_path)
    missing_columns = sorted(EXPECTED_COLUMNS - set(fields))
    if missing_columns:
        raise ValueError(
            "CSV CAIXA sem colunas necessárias: " + ", ".join(missing_columns)
        )
    if not rows:
        raise ValueError("O CSV CAIXA não contém registros.")

    counts: Counter[str] = Counter()
    target_values: list[float] = []
    candidate_records: list[dict[str, Any]] = []
    collection_dates: set[str] = set()
    appraisal_dates: set[str] = set()
    target_per_m2_relative_errors: list[float] = []
    invalid_rows_by_reason: Counter[str] = Counter()
    ids = [row["n_do_imovel"] for row in rows if row["n_do_imovel"]]

    for row in rows:
        property_type = row["tipo"].strip().casefold()
        city = row["cidade"].strip().casefold()
        nature = row["natureza_do_valor"].strip().casefold()
        source = row["fonte"].strip().casefold()
        area_type = row["area_tipo"].strip().casefold()
        area = _number(row["area_ref_m2"])
        target = _number(row["valor_avaliacao_brl"])
        target_per_m2 = _number(row["avaliacao_brl_m2"])

        counts[f"property_type:{property_type or 'missing'}"] += 1
        counts[f"target_nature:{nature or 'missing'}"] += 1
        counts[f"source:{source or 'missing'}"] += 1
        counts[f"area_type:{area_type or 'missing'}"] += 1
        if _valid_date(row["data_coleta"]):
            counts["valid_collection_date"] += 1
            collection_dates.add(row["data_coleta"][:10])
        if _valid_date(row["avaliacao_data"]):
            counts["valid_appraisal_date"] += 1
            appraisal_dates.add(row["avaliacao_data"][:10])
        bedrooms = _number(row["quartos"])
        parking = _number(row["vagas"])
        if bedrooms is not None and bedrooms >= 0 and bedrooms.is_integer():
            counts["bedrooms_present"] += 1
        else:
            counts["bedrooms_missing_or_invalid"] += 1
        if parking is not None and parking >= 0 and parking.is_integer():
            counts["parking_spaces_present"] += 1
        else:
            counts["parking_spaces_missing_or_invalid"] += 1
        if target is not None and target > 0:
            target_values.append(target)
        else:
            invalid_rows_by_reason["invalid_appraisal_target"] += 1

        if area is not None and area > 0 and target and target_per_m2 and target > 0:
            target_per_m2_relative_errors.append(
                abs(target_per_m2 - target / area) / (target / area)
            )

        candidate_errors = []
        if property_type not in {"apartamento", "apartment"}:
            candidate_errors.append("unsupported_property_type")
        if city not in {"sao paulo", "são paulo"}:
            candidate_errors.append("outside_model_geography")
        if area_type not in {"privativa", "private"}:
            candidate_errors.append("area_definition_not_private")
        if area is None or not MIN_AREA_M2 <= area <= MAX_AREA_M2:
            candidate_errors.append("area_missing_or_out_of_range")
        if target is None or target <= 0:
            candidate_errors.append("invalid_appraisal_target")
        if nature != "avaliacao_caixa_imovel_retomado":
            candidate_errors.append("target_nature_not_confirmed_caixa_appraisal")
        if source != "caixa_lista_imoveis_oficial":
            candidate_errors.append("source_not_identified_as_caixa_official")

        for error in candidate_errors:
            invalid_rows_by_reason[error] += 1
        if not candidate_errors:
            neighborhood = row["bairro"].strip().casefold()
            if not neighborhood:
                invalid_rows_by_reason["missing_neighborhood_for_spatial_validation"] += 1
                continue
            candidate_records.append(
                {
                    "area_m2": area,
                    "target": target,
                    "neighborhood": neighborhood,
                    "bedrooms": (
                        int(bedrooms)
                        if bedrooms is not None
                        and bedrooms >= 0
                        and bedrooms.is_integer()
                        else None
                    ),
                    "parking": (
                        int(parking)
                        if parking is not None
                        and parking >= 0
                        and parking.is_integer()
                        else None
                    ),
                    "appraisal_date": (
                        date.fromisoformat(row["avaliacao_data"][:10])
                        if _valid_date(row["avaliacao_data"])
                        else None
                    ),
                    "property_key": row["n_do_imovel"],
                }
            )

    if not target_values:
        raise ValueError("Nenhum valor de avaliação positivo e numérico foi encontrado.")
    spatial_validation = (
        _spatial_baseline_validation(candidate_records)
        if candidate_records
        else None
    )
    feature_validation = (
        _feature_incremental_validation(candidate_records)
        if candidate_records
        else None
    )
    temporal_validation = _temporal_holdout_validation(candidate_records)
    target_sorted = sorted(target_values)
    target_summary = {
        "valid_positive_targets": len(target_values),
        "min_brl": round(target_sorted[0], 2),
        "median_brl": round(_median(target_values), 2),
        "max_brl": round(target_sorted[-1], 2),
    }
    date_coverage = counts["valid_appraisal_date"]
    sample_hash = hashlib.sha256(input_path.read_bytes()).hexdigest()

    return {
        "dataset_id": "caixa_sp_appraisal_validation_candidate",
        "input_file": input_path.name,
        "status": "candidate_for_expert_review_not_approved_for_operational_use",
        "record_count": len(rows),
        "candidate_rows_for_spatial_validation": len(candidate_records),
        "validation_rows_excluded_from_spatial_candidate": (
            len(rows) - len(candidate_records)
        ),
        "target": {
            "column": "valor_avaliacao_brl",
            "definition_in_source": "avaliacao_caixa_imovel_retomado",
            "unit": "BRL",
            "target_summary": target_summary,
        },
        "quality": {
            "counts": dict(sorted(counts.items())),
            "invalid_rows_by_reason": dict(sorted(invalid_rows_by_reason.items())),
            "unique_property_ids": len(set(ids)),
            "duplicate_property_id_groups": sum(
                count > 1 for count in Counter(ids).values()
            ),
            "appraisal_date_coverage_percent": round(
                date_coverage / len(rows) * 100, 2
            ),
            "target_per_m2_matches_target_divided_by_area_rows": sum(
                error <= 0.01 for error in target_per_m2_relative_errors
            ),
            "target_per_m2_checked_rows": len(target_per_m2_relative_errors),
            "bedrooms_coverage_percent": round(
                counts["bedrooms_present"] / len(rows) * 100, 2
            ),
            "parking_spaces_coverage_percent": round(
                counts["parking_spaces_present"] / len(rows) * 100, 2
            ),
            "collection_date_distinct_values": len(collection_dates),
            "appraisal_date_distinct_values": len(appraisal_dates),
        },
        "spatial_baseline_validation": spatial_validation,
        "feature_incremental_validation": feature_validation,
        "temporal_validation": temporal_validation,
        "attribute_inventory": [
            {
                "attribute": "area_ref_m2",
                "definition": "Área declarada como privativa no arquivo, m²",
                "available_rows": sum(
                    1 for row in candidate_records if row["area_m2"] > 0
                ),
                "classification": "extraido_sem_documentacao_independente",
                "operation_path": "Matrícula/documento da unidade ou campo validado na solicitação CAIXA.",
                "recommendation": "Usar somente após confirmar definição, unidade e vínculo com a unidade.",
            },
            {
                "attribute": "quartos",
                "definition": "Quantidade de dormitórios da unidade",
                "available_rows": counts["bedrooms_present"],
                "classification": "extraido_com_evidencia_da_unidade_pendente",
                "operation_path": "Documento/planta/anúncio da mesma unidade, com vínculo e evidência arquivados.",
                "recommendation": "Não completar por equivalência com área; manter ausente se não comprovado.",
            },
            {
                "attribute": "vagas",
                "definition": "Quantidade de vagas associadas à unidade",
                "available_rows": counts["parking_spaces_present"],
                "classification": "extraido_com_evidencia_da_unidade_pendente",
                "operation_path": "Matrícula/documento da vaga ou campo validado na solicitação CAIXA.",
                "recommendation": "Não tratar vaga do edifício como vaga privativa da unidade.",
            },
            {
                "attribute": "banheiros",
                "definition": "Quantidade de banheiros da unidade",
                "available_rows": 0,
                "classification": "ausente",
                "operation_path": "Documento/planta da unidade, se disponível no fluxo CAIXA.",
                "recommendation": "Solicitar dado ou manter ausente; não estimar sem amostra de validação independente.",
            },
            {
                "attribute": "elevador",
                "definition": "Existência de elevador no edifício/bloco",
                "available_rows": 0,
                "classification": "ausente",
                "operation_path": "Documento ou cadastro do edifício identificado por torre/bloco.",
                "recommendation": "Não inferir por anúncio de outra unidade sem provar mesmo edifício/bloco.",
            },
            {
                "attribute": "idade_construcao",
                "definition": "Idade em anos na data-base da avaliação",
                "available_rows": 0,
                "classification": "ausente",
                "operation_path": "Ano de construção de fonte/documento válido e data-base recebida na operação.",
                "recommendation": "Calcular apenas com fonte do ano e data-base documentadas.",
            },
            {
                "attribute": "conservacao_condominio",
                "definition": "Estado de conservação do condomínio/edifício",
                "available_rows": 0,
                "classification": "ausente",
                "operation_path": "Inspeção ou evidência atual do edifício, caso requisito seja confirmado.",
                "recommendation": "Não inferir por idade, preço ou imagem isolada.",
            },
            {
                "attribute": "avaliacao_data",
                "definition": "Data-base do valor de avaliação",
                "available_rows": counts["valid_appraisal_date"],
                "classification": "ausente_no_lote_atual",
                "operation_path": "Laudo/documento da avaliação CAIXA.",
                "recommendation": "Obrigatória para validação temporal; data de coleta não substitui.",
            },
        ],
        "limitations": [
            "O campo avaliacao_data está ausente no lote; não é possível fazer validação temporal.",
            "A origem está rotulada como lista oficial CAIXA, mas autorização, finalidade, metodologia e laudo da avaliação precisam de confirmação documental.",
            "A coleta é um único retrato temporal de imóveis retomados/ofertados, não uma amostra representativa de todo o mercado nem prova de valor transacionado.",
            "preco_venda_brl e desconto_pct foram excluídos como preditores para evitar mistura/leakage com o alvo de avaliação.",
            "avaliacao_brl_m2 é matematicamente derivado do alvo e da área e não foi usado como preditor.",
            "A validação espacial é um benchmark interno nesta mesma fonte; não equivale à validação independente nem à homologação CAIXA.",
            "Endereço, identificador do imóvel, link e SQL não são incluídos nos relatórios derivados; acesso e retenção da fonte devem seguir as regras da CAIXA.",
        ],
        "release_decision": {
            "appraisal_training_enabled": False,
            "operational_prediction_enabled": False,
            "expert_review_required": True,
            "reason": (
                "O lote fornece rótulos candidatos e permite um benchmark espacial "
                "exploratório, mas data-base da avaliação, método, autorização e "
                "representatividade ainda não estão validados."
            ),
        },
        "source": {
            "sha256": sample_hash,
            "delimiter": delimiter,
            "collection_date_coverage": counts["valid_collection_date"],
            "appraisal_date_coverage": date_coverage,
            "collection_dates": sorted(collection_dates),
            "appraisal_dates": sorted(appraisal_dates),
        },
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = audit_dataset(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Auditoria CAIXA: {report['record_count']} registros; "
        f"candidatos espaciais={report['candidate_rows_for_spatial_validation']}; "
        f"data de avaliação={report['quality']['appraisal_date_coverage_percent']:.1f}%; "
        "uso operacional=False"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
