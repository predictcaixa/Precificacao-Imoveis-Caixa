"""Independently verify the CAIXA audit calculations against the source CSV."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

if __package__:
    from .audit_caixa_validation import (
        DEFAULT_INPUT as DEFAULT_SOURCE,
        DEFAULT_OUTPUT as DEFAULT_AUDIT,
        MAX_AREA_M2,
        MIN_AREA_M2,
        SPATIAL_FOLDS,
    )
else:
    from audit_caixa_validation import (
        DEFAULT_INPUT as DEFAULT_SOURCE,
        DEFAULT_OUTPUT as DEFAULT_AUDIT,
        MAX_AREA_M2,
        MIN_AREA_M2,
        SPATIAL_FOLDS,
    )


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    BASE_DIR / "scripts" / "dados" / "caixa_sp_validacao_calculation_check.json"
)


def _read_number(value: str | None) -> float | None:
    if not value:
        return None
    try:
        result = float(value.strip())
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def _read_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _percentile_floor(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    return ordered[int((len(ordered) - 1) * percentile)]


def _reference_metrics(
    actual: list[float], predicted: list[float]
) -> dict[str, float]:
    if not actual or len(actual) != len(predicted) or any(value <= 0 for value in actual):
        raise ValueError("A simulação requer valores-alvo positivos e previsões pareadas.")
    errors = [abs(y - p) for y, p in zip(actual, predicted)]
    absolute_percentage_errors = [e / y for e, y in zip(errors, actual)]
    total_sum_squares = sum((y - statistics.mean(actual)) ** 2 for y in actual)
    residual_sum_squares = sum((y - p) ** 2 for y, p in zip(actual, predicted))
    smape = [
        200 * e / (abs(y) + abs(p))
        for y, p, e in zip(actual, predicted, errors)
        if abs(y) + abs(p) > 0
    ]
    return {
        "mae_brl": round(sum(errors) / len(errors), 2),
        "rmse_brl": round(math.sqrt(sum(e * e for e in errors) / len(errors)), 2),
        "median_absolute_percentage_error_percent": round(
            statistics.median(absolute_percentage_errors) * 100, 4
        ),
        "p90_absolute_percentage_error_percent": round(
            _percentile_floor(absolute_percentage_errors, 0.9) * 100, 4
        ),
        "wape_percent": round(sum(errors) / sum(actual) * 100, 4),
        "smape_percent": round(statistics.mean(smape), 4),
        "r2": round(
            1 - residual_sum_squares / total_sum_squares
            if total_sum_squares
            else 0,
            6,
        ),
    }


def _get_source_records(source_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    with source_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    eligible: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    for row in rows:
        area = _read_number(row.get("area_ref_m2"))
        target = _read_number(row.get("valor_avaliacao_brl"))
        bedrooms = _read_number(row.get("quartos"))
        parking = _read_number(row.get("vagas"))
        property_type = (row.get("tipo") or "").strip().casefold()
        city = (row.get("cidade") or "").strip().casefold()
        area_type = (row.get("area_tipo") or "").strip().casefold()
        value_nature = (row.get("natureza_do_valor") or "").strip().casefold()
        source = (row.get("fonte") or "").strip().casefold()
        accepted = (
            property_type in {"apartamento", "apartment"}
            and city in {"sao paulo", "são paulo"}
            and area_type in {"privativa", "private"}
            and area is not None
            and MIN_AREA_M2 <= area <= MAX_AREA_M2
            and target is not None
            and target > 0
            and value_nature == "avaliacao_caixa_imovel_retomado"
            and source == "caixa_lista_imoveis_oficial"
        )
        if not accepted:
            continue
        bedrooms_valid = bedrooms is not None and bedrooms >= 0 and bedrooms.is_integer()
        parking_valid = parking is not None and parking >= 0 and parking.is_integer()
        appraisal_date = _read_date(row.get("avaliacao_data"))
        record = {
            "area_m2": area,
            "target": target,
            "neighborhood": (row.get("bairro") or "").strip().casefold(),
            "bedrooms": int(bedrooms) if bedrooms_valid else None,
            "parking": int(parking) if parking_valid else None,
            "appraisal_date": appraisal_date,
            "property_key": (row.get("n_do_imovel") or "").strip(),
            "raw": row,
        }
        eligible.append(record)
        if record["neighborhood"]:
            records.append(record)
    return rows, records


def _expected_exclusion_counts(rows: list[dict[str, str]]) -> Counter[str]:
    excluded: Counter[str] = Counter()
    for row in rows:
        property_type = (row.get("tipo") or "").strip().casefold()
        city = (row.get("cidade") or "").strip().casefold()
        area_type = (row.get("area_tipo") or "").strip().casefold()
        nature = (row.get("natureza_do_valor") or "").strip().casefold()
        source = (row.get("fonte") or "").strip().casefold()
        area = _read_number(row.get("area_ref_m2"))
        target = _read_number(row.get("valor_avaliacao_brl"))
        reasons = []
        if property_type not in {"apartamento", "apartment"}:
            reasons.append("unsupported_property_type")
        if city not in {"sao paulo", "são paulo"}:
            reasons.append("outside_model_geography")
        if area_type not in {"privativa", "private"}:
            reasons.append("area_definition_not_private")
        if area is None or not MIN_AREA_M2 <= area <= MAX_AREA_M2:
            reasons.append("area_missing_or_out_of_range")
        if target is None or target <= 0:
            reasons.append("invalid_appraisal_target")
        if nature != "avaliacao_caixa_imovel_retomado":
            reasons.append("target_nature_not_confirmed_caixa_appraisal")
        if source != "caixa_lista_imoveis_oficial":
            reasons.append("source_not_identified_as_caixa_official")
        excluded.update(reasons)
        if not reasons and not (row.get("bairro") or "").strip():
            excluded["missing_neighborhood_for_spatial_validation"] += 1
    return excluded


def _folds(records: list[dict[str, Any]]) -> list[int]:
    sizes: dict[str, int] = defaultdict(int)
    for item in records:
        sizes[item["neighborhood"]] += 1
    if len(sizes) < SPATIAL_FOLDS:
        raise ValueError("Não há bairros suficientes para refazer a validação espacial.")
    fold_sizes = [0] * SPATIAL_FOLDS
    assignment: dict[str, int] = {}
    for neighborhood in sorted(sizes, key=lambda group: (-sizes[group], group)):
        fold = min(range(SPATIAL_FOLDS), key=lambda candidate: fold_sizes[candidate])
        assignment[neighborhood] = fold
        fold_sizes[fold] += sizes[neighborhood]
    return [assignment[row["neighborhood"]] for row in records]


def _expected_spatial(records: list[dict[str, Any]]) -> tuple[dict[str, Any], list[int]]:
    fold_ids = _folds(records)
    target_values = [row["target"] for row in records]
    predictions: dict[str, list[float]] = {
        "training_citywide_median": [0.0] * len(records),
        "training_median_per_m2_times_private_area": [0.0] * len(records),
    }
    fold_rows = []
    for fold in range(SPATIAL_FOLDS):
        tests = [i for i, current in enumerate(fold_ids) if current == fold]
        trains = [i for i, current in enumerate(fold_ids) if current != fold]
        median_value = statistics.median(target_values[i] for i in trains)
        median_rate = statistics.median(
            target_values[i] / records[i]["area_m2"] for i in trains
        )
        for index in tests:
            predictions["training_citywide_median"][index] = median_value
            predictions["training_median_per_m2_times_private_area"][index] = (
                median_rate * records[index]["area_m2"]
            )
        train_neighborhoods = {records[i]["neighborhood"] for i in trains}
        test_neighborhoods = {records[i]["neighborhood"] for i in tests}
        fold_rows.append(
            {
                "training_rows": len(trains),
                "test_rows": len(tests),
                "training_neighborhoods": len(train_neighborhoods),
                "test_neighborhoods": len(test_neighborhoods),
                "neighborhood_overlap": bool(train_neighborhoods & test_neighborhoods),
            }
        )
    expected_metrics = {
        model: _reference_metrics(target_values, prediction)
        for model, prediction in predictions.items()
    }
    return {"folds": fold_rows, "metrics": expected_metrics}, fold_ids


def _area_band(area: float) -> str:
    return (
        "le_40" if area <= 40 else
        "40_60" if area <= 60 else
        "60_80" if area <= 80 else
        "80_120" if area <= 120 else
        "gt_120"
    )


def _expected_feature_comparison(
    records: list[dict[str, Any]], fold_ids: list[int]
) -> dict[str, Any]:
    complete = [
        i for i, row in enumerate(records)
        if row["bedrooms"] is not None and row["parking"] is not None
    ]
    baseline_y: list[float] = []
    baseline_p: list[float] = []
    enriched_y: list[float] = []
    enriched_p: list[float] = []
    fallback_count = 0
    for fold in range(SPATIAL_FOLDS):
        train = [i for i, current in enumerate(fold_ids) if current != fold]
        test = [i for i in complete if fold_ids[i] == fold]
        global_rate = statistics.median(
            records[i]["target"] / records[i]["area_m2"] for i in train
        )
        complete_train = [
            i for i in train
            if records[i]["bedrooms"] is not None
            and records[i]["parking"] is not None
        ]
        group_values: dict[tuple[str, int, int], list[float]] = defaultdict(list)
        for index in complete_train:
            row = records[index]
            group_values[
                (_area_band(row["area_m2"]), row["bedrooms"], row["parking"])
            ].append(row["target"])
        group_medians = {
            key: statistics.median(values)
            for key, values in group_values.items()
            if len(values) >= 5
        }
        for index in test:
            row = records[index]
            key = (_area_band(row["area_m2"]), row["bedrooms"], row["parking"])
            prediction = group_medians.get(key)
            if prediction is None:
                prediction = global_rate * row["area_m2"]
                fallback_count += 1
            baseline_y.append(row["target"])
            baseline_p.append(global_rate * row["area_m2"])
            enriched_y.append(row["target"])
            enriched_p.append(prediction)
    return {
        "complete_rows": len(complete),
        "baseline_metrics": _reference_metrics(baseline_y, baseline_p),
        "enriched_metrics": _reference_metrics(enriched_y, enriched_p),
        "fallback_rows": fallback_count,
    }


def _add_check(
    checks: list[dict[str, Any]],
    name: str,
    expected: Any,
    actual: Any,
    *,
    tolerance: float = 0,
) -> None:
    if isinstance(expected, (float, int)) and isinstance(actual, (float, int)):
        passed = math.isclose(
            float(expected), float(actual), rel_tol=1e-8, abs_tol=tolerance
        )
    else:
        passed = expected == actual
    checks.append(
        {
            "check": name,
            "passed": passed,
            "expected": expected,
            "reported": actual,
        }
    )


def validate_report(source_path: Path, audit: dict[str, Any]) -> dict[str, Any]:
    all_rows, records = _get_source_records(source_path)
    checks: list[dict[str, Any]] = []
    all_targets = [
        target
        for row in all_rows
        if (target := _read_number(row.get("valor_avaliacao_brl"))) is not None
        and target > 0
    ]
    target_sorted = sorted(all_targets)
    area_rate_matches = 0
    area_rate_checked = 0
    for row in all_rows:
        area = _read_number(row.get("area_ref_m2"))
        target = _read_number(row.get("valor_avaliacao_brl"))
        rate = _read_number(row.get("avaliacao_brl_m2"))
        if area and target and rate and area > 0 and target > 0:
            area_rate_checked += 1
            if abs(rate - target / area) / (target / area) <= 0.01:
                area_rate_matches += 1

    _add_check(checks, "source_row_count", len(all_rows), audit["record_count"])
    _add_check(
        checks,
        "spatial_candidate_count",
        len(records),
        audit["candidate_rows_for_spatial_validation"],
    )
    _add_check(
        checks, "target_positive_count", len(all_targets),
        audit["target"]["target_summary"]["valid_positive_targets"],
    )
    for name, value in (
        ("target_min_brl", target_sorted[0]),
        ("target_median_brl", statistics.median(all_targets)),
        ("target_max_brl", target_sorted[-1]),
    ):
        _add_check(
            checks, name, round(value, 2),
            audit["target"]["target_summary"][name.removeprefix("target_")],
            tolerance=0.01,
        )

    expected_spatial, fold_ids = _expected_spatial(records)
    spatial = audit["spatial_baseline_validation"]
    _add_check(
        checks, "spatial_rows_evaluated", len(records), spatial["rows_evaluated"]
    )
    _add_check(
        checks,
        "spatial_neighborhood_count",
        len({row["neighborhood"] for row in records}),
        spatial["neighborhoods_evaluated"],
    )
    _add_check(
        checks,
        "spatial_fold_count",
        SPATIAL_FOLDS,
        len(spatial["folds"]),
    )
    for index, expected in enumerate(expected_spatial["folds"]):
        actual = spatial["folds"][index]
        for key, value in expected.items():
            _add_check(checks, f"fold_{index + 1}_{key}", value, actual[key])
    for model_key, expected_metrics in expected_spatial["metrics"].items():
        actual_metrics = spatial["estimators"][model_key]["out_of_fold_metrics"]
        for metric, value in expected_metrics.items():
            _add_check(
                checks,
                f"spatial_{model_key}_{metric}",
                value,
                actual_metrics[metric],
                tolerance=0.00011,
            )

    feature = _expected_feature_comparison(records, fold_ids)
    feature_report = audit["feature_incremental_validation"]
    _add_check(
        checks,
        "feature_complete_case_count",
        feature["complete_rows"],
        feature_report["rows_with_area_bedrooms_and_parking"],
    )
    _add_check(
        checks,
        "feature_fallback_count",
        feature["fallback_rows"],
        feature_report["enriched_group_prediction_fallback_rows"],
    )
    for model_key, key in (
        ("baseline_metrics", "baseline_area_rate"),
        ("enriched_metrics", "area_bedrooms_parking_groups"),
    ):
        actual_metrics = feature_report[key]
        for metric, value in feature[model_key].items():
            _add_check(
                checks,
                f"feature_{key}_{metric}",
                value,
                actual_metrics[metric],
                tolerance=0.00011,
            )

    quality = audit["quality"]
    bedroom_count = sum(
        _read_number(row.get("quartos")) is not None
        and _read_number(row.get("quartos")) >= 0
        and _read_number(row.get("quartos")).is_integer()
        for row in all_rows
    )
    parking_count = sum(
        _read_number(row.get("vagas")) is not None
        and _read_number(row.get("vagas")) >= 0
        and _read_number(row.get("vagas")).is_integer()
        for row in all_rows
    )
    _add_check(
        checks,
        "independent_bedrooms_count",
        bedroom_count,
        quality["counts"]["bedrooms_present"],
    )
    _add_check(
        checks,
        "independent_parking_count",
        parking_count,
        quality["counts"]["parking_spaces_present"],
    )
    _add_check(
        checks, "bedroom_coverage_percent",
        round(quality["counts"]["bedrooms_present"] / len(all_rows) * 100, 2),
        quality["bedrooms_coverage_percent"],
    )
    _add_check(
        checks, "parking_coverage_percent",
        round(quality["counts"]["parking_spaces_present"] / len(all_rows) * 100, 2),
        quality["parking_spaces_coverage_percent"],
    )
    _add_check(
        checks, "target_per_m2_match_count",
        area_rate_matches,
        quality["target_per_m2_matches_target_divided_by_area_rows"],
    )
    _add_check(
        checks, "target_per_m2_checked_rows",
        area_rate_checked,
        quality["target_per_m2_checked_rows"],
    )
    appraisal_dates = {
        _read_date(row.get("avaliacao_data"))
        for row in all_rows
        if _read_date(row.get("avaliacao_data")) is not None
    }
    collection_dates = {
        _read_date(row.get("data_coleta"))
        for row in all_rows
        if _read_date(row.get("data_coleta")) is not None
    }
    _add_check(
        checks, "appraisal_date_coverage_count", len([
            row for row in all_rows if _read_date(row.get("avaliacao_data"))
        ]), quality["counts"].get("valid_appraisal_date", 0)
    )
    _add_check(
        checks, "appraisal_date_coverage_percent",
        round(
            quality["counts"].get("valid_appraisal_date", 0) / len(all_rows) * 100,
            2,
        ),
        quality["appraisal_date_coverage_percent"],
    )
    _add_check(
        checks, "collection_date_distinct_count", len(collection_dates),
        quality["collection_date_distinct_values"]
    )
    _add_check(
        checks, "appraisal_date_distinct_count", len(appraisal_dates),
        quality["appraisal_date_distinct_values"]
    )
    property_ids = [
        row["n_do_imovel"].strip()
        for row in all_rows
        if row.get("n_do_imovel", "").strip()
    ]
    id_frequencies = Counter(property_ids)
    _add_check(
        checks,
        "unique_property_id_count",
        len(id_frequencies),
        quality["unique_property_ids"],
    )
    _add_check(
        checks,
        "duplicate_property_id_group_count",
        sum(frequency > 1 for frequency in id_frequencies.values()),
        quality["duplicate_property_id_groups"],
    )
    count_categories = {
        "property_type": "tipo",
        "target_nature": "natureza_do_valor",
        "source": "fonte",
        "area_type": "area_tipo",
    }
    for category, column in count_categories.items():
        expected_counts = Counter(
            (row.get(column) or "").strip().casefold() or "missing"
            for row in all_rows
        )
        for label, expected_count in expected_counts.items():
            _add_check(
                checks,
                f"quality_count_{category}_{label}",
                expected_count,
                quality["counts"].get(f"{category}:{label}", 0),
            )
    for field, output_key in (
        ("data_coleta", "valid_collection_date"),
        ("avaliacao_data", "valid_appraisal_date"),
    ):
        valid_count = sum(_read_date(row.get(field)) is not None for row in all_rows)
        _add_check(
            checks,
            f"quality_count_{output_key}",
            valid_count,
            quality["counts"].get(output_key, 0),
        )
    _add_check(
        checks,
        "excluded_spatial_candidate_count",
        int(audit["record_count"]) - len(records),
        audit["validation_rows_excluded_from_spatial_candidate"],
    )
    expected_exclusions = _expected_exclusion_counts(all_rows)
    _add_check(
        checks,
        "candidate_exclusion_reasons",
        dict(sorted(expected_exclusions.items())),
        audit["quality"]["invalid_rows_by_reason"],
    )
    _add_check(
        checks,
        "area_coverage_candidate_rows",
        len(records),
        audit["attribute_inventory"][0]["available_rows"],
    )
    attribute_rows = {
        attribute["attribute"]: attribute["available_rows"]
        for attribute in audit["attribute_inventory"]
    }
    for attribute_name, expected_count in (
        ("quartos", bedroom_count),
        ("vagas", parking_count),
        ("avaliacao_data", quality["counts"].get("valid_appraisal_date", 0)),
    ):
        _add_check(
            checks,
            f"attribute_inventory_{attribute_name}",
            expected_count,
            attribute_rows[attribute_name],
        )
    _add_check(
        checks,
        "feature_complete_case_coverage_percent",
        round(
            feature["complete_rows"] / len(records) * 100 if records else 0,
            2,
        ),
        feature_report["complete_case_coverage_percent"],
    )
    temporal = audit["temporal_validation"]
    _add_check(
        checks,
        "temporal_dated_candidate_count",
        sum(row["appraisal_date"] is not None for row in records),
        temporal["dated_candidate_rows"],
    )
    _add_check(
        checks,
        "temporal_distinct_appraisal_dates",
        len({row["appraisal_date"] for row in records if row["appraisal_date"]}),
        temporal["distinct_appraisal_dates"],
    )
    _add_check(
        checks,
        "source_collection_date_coverage",
        quality["counts"].get("valid_collection_date", 0),
        audit["source"]["collection_date_coverage"],
    )
    _add_check(
        checks,
        "source_appraisal_date_coverage",
        quality["counts"].get("valid_appraisal_date", 0),
        audit["source"]["appraisal_date_coverage"],
    )
    _add_check(
        checks, "temporal_validation_blocked_without_dates",
        not appraisal_dates,
        not audit["temporal_validation"]["temporal_validation_possible"],
    )
    _add_check(
        checks, "operational_prediction_remains_blocked",
        False, audit["release_decision"]["operational_prediction_enabled"]
    )
    _add_check(
        checks, "audit_sha256_matches_source",
        hashlib.sha256(source_path.read_bytes()).hexdigest(),
        audit["source"]["sha256"],
    )

    checks.extend(
        [
            {
                "check": "simulation_hand_example_mae",
                "passed": _reference_metrics([100, 200, 300], [90, 220, 300])["mae_brl"] == 10,
                "expected": 10,
                "reported": _reference_metrics([100, 200, 300], [90, 220, 300])["mae_brl"],
            },
            {
                "check": "simulation_hand_example_wape",
                "passed": _reference_metrics([100, 200, 300], [90, 220, 300])["wape_percent"] == 5,
                "expected": 5,
                "reported": _reference_metrics([100, 200, 300], [90, 220, 300])["wape_percent"],
            },
            {
                "check": "simulation_hand_example_r2",
                "passed": _reference_metrics([100, 200, 300], [90, 220, 300])["r2"] == 0.975,
                "expected": 0.975,
                "reported": _reference_metrics([100, 200, 300], [90, 220, 300])["r2"],
            },
        ]
    )
    failed = [check for check in checks if not check["passed"]]
    return {
        "status": "passed" if not failed else "failed",
        "source_file": source_path.name,
        "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "audit_file": DEFAULT_AUDIT.name,
        "rows_checked": len(all_rows),
        "eligible_records_checked": len(records),
        "checks_passed": len(checks) - len(failed),
        "checks_failed": len(failed),
        "checks": checks,
        "privacy": "No property IDs, addresses, URLs, SQLs, or row-level outputs are included.",
        "methodology": (
            "Recomputed counts, target aggregates, coverage, target-per-area arithmetic, "
            "spatial folds and their metrics, feature comparison and temporal gating "
            "from the raw CSV with an independent reference implementation. The hand "
            "simulation uses y=[100,200,300], predictions=[90,220,300]."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if not args.audit.is_file():
        raise FileNotFoundError(
            f"Auditoria não encontrada: {args.audit}. Execute primeiro "
            "scripts\\audit_caixa_validation.py."
        )
    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    report = validate_report(args.source, audit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Validação independente: {report['checks_passed']}/"
        f"{report['checks_passed'] + report['checks_failed']} cálculos; "
        f"falhas={report['checks_failed']}; status={report['status']}"
    )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
