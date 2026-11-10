"""Build and query an experimental ITBI comparable-price reference."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.audit_data_sources import (
    BASE_DIR,
    DATA_DIR,
    OFFICIAL_FILE,
    OFFICIAL_SHEET,
    _excel_serial_date,
    _transaction_key,
    iter_xlsx_rows,
    normalize_value,
)


OUTPUT_PATH = BASE_DIR / "models" / "itbi_reference_2026.json"
MIN_AREA_M2 = 15.0
MAX_AREA_M2 = 1000.0
MIN_COMPARABLES = 30
VALID_PATTERN_CODES = {str(code) for code in range(20, 26)}
REFERENCE_YEAR = "2026"


def normalize_cep_prefix(value: object) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits:
        return ""
    if len(digits) == 5:
        return digits
    if 6 <= len(digits) <= 8:
        return digits.zfill(8)[:5]
    raise ValueError("Informe um prefixo de CEP com 5 dígitos ou um CEP de até 8 dígitos.")


def _number(value: str) -> Decimal | None:
    try:
        number = Decimal(value.strip().replace(",", "."))
    except (InvalidOperation, AttributeError):
        return None
    return number if number.is_finite() else None


def _profile(values: list[float]) -> dict[str, float | int]:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("Não há comparáveis para calcular o perfil.")

    def quantile(probability: float) -> float:
        index = int((len(ordered) - 1) * probability)
        return round(ordered[index], 6)

    return {
        "count": len(ordered),
        "p10_brl_per_m2": quantile(0.10),
        "median_brl_per_m2": quantile(0.50),
        "p90_brl_per_m2": quantile(0.90),
    }


def _eligible_records(data_dir: Path = DATA_DIR) -> tuple[list[dict[str, Any]], dict[str, int]]:
    source_path = data_dir / OFFICIAL_FILE
    if not source_path.is_file():
        raise FileNotFoundError(f"Arquivo necessário não encontrado: {source_path}")

    qualified: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for row in iter_xlsx_rows(source_path, OFFICIAL_SHEET):
        transaction_date = _excel_serial_date(row.get("Data de Transação", ""))
        if not transaction_date or not transaction_date.startswith(REFERENCE_YEAR):
            continue
        counts["transactions_in_reference_year"] += 1

        if row.get("Natureza de Transação", "").strip() != "1.Compra e venda":
            counts["excluded_other_nature"] += 1
            continue
        if row.get("Situação do SQL", "").strip() != "Ativo Predial":
            counts["excluded_inactive_sql"] += 1
            continue
        if row.get("Uso (IPTU)", "").strip() != "20":
            counts["excluded_other_use"] += 1
            continue
        if _number(row.get("Proporção Transmitida (%)", "")) != Decimal("100"):
            counts["excluded_partial_transfer"] += 1
            continue

        price = _number(
            row.get("Valor de Transação (declarado pelo contribuinte)", "")
        )
        area = _number(row.get("Área Construída (m2)", ""))
        if (
            price is None
            or price <= 0
            or area is None
            or area < Decimal(str(MIN_AREA_M2))
            or area > Decimal(str(MAX_AREA_M2))
        ):
            counts["excluded_invalid_price_or_area"] += 1
            continue

        pattern_code = normalize_value(row.get("Padrão (IPTU)", ""), "number")
        if pattern_code not in VALID_PATTERN_CODES:
            counts["excluded_unrecognized_iptu_pattern"] += 1
            continue

        key = _transaction_key(row)
        if not all(key):
            counts["excluded_incomplete_join_key"] += 1
            continue

        cep = re.sub(r"\D", "", row.get("CEP", ""))
        cep_prefix = cep.zfill(8)[:5] if 6 <= len(cep) <= 8 else ""
        qualified.append(
            {
                "key": key,
                "sql": normalize_value(row.get("N° do Cadastro (SQL)", ""), "text"),
                "date": transaction_date,
                "price": float(price),
                "area": float(area),
                "price_per_m2": float(price / area),
                "cep_prefix5": cep_prefix,
                "iptu_pattern_code": pattern_code,
            }
        )

    key_counts = Counter(record["key"] for record in qualified)
    unique = [record for record in qualified if key_counts[record["key"]] == 1]
    counts["qualified_before_ambiguous_exclusion"] = len(qualified)
    counts["ambiguous_rows_excluded"] = len(qualified) - len(unique)
    counts["unique_eligible_transactions"] = len(unique)
    if not unique:
        raise ValueError("Nenhuma transação elegível encontrada na fonte ITBI.")
    return unique, dict(counts)


def _profiles(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_cep_pattern: dict[str, list[float]] = defaultdict(list)
    by_cep: dict[str, list[float]] = defaultdict(list)
    by_pattern: dict[str, list[float]] = defaultdict(list)
    all_rates: list[float] = []
    for record in records:
        rate = record["price_per_m2"]
        pattern = record["iptu_pattern_code"]
        by_pattern[pattern].append(rate)
        all_rates.append(rate)
        if record["cep_prefix5"]:
            by_cep_pattern[f"{record['cep_prefix5']}|{pattern}"].append(rate)
            by_cep[record["cep_prefix5"]].append(rate)

    return {
        "by_cep_prefix5_and_iptu_pattern": {
            key: _profile(values) for key, values in sorted(by_cep_pattern.items())
        },
        "by_cep_prefix5": {
            key: _profile(values) for key, values in sorted(by_cep.items())
        },
        "by_iptu_pattern_citywide": {
            key: _profile(values) for key, values in sorted(by_pattern.items())
        },
        "citywide": _profile(all_rates),
    }


def _backtest(records: list[dict[str, Any]]) -> dict[str, Any]:
    training = [record for record in records if record["date"][5:7] <= "06"]
    training_sql = {record["sql"] for record in training}
    test = [
        record
        for record in records
        if record["date"][5:7] >= "07" and record["sql"] not in training_sql
    ]
    if not training or not test:
        raise ValueError("Dados insuficientes para a validação temporal de 2026.")

    profiles = _profiles(training)
    predictions: list[float] = []
    actuals: list[float] = []
    range_hits = 0
    scope_counts: Counter[str] = Counter()

    for record in test:
        pattern = record["iptu_pattern_code"]
        cep_key = f"{record['cep_prefix5']}|{pattern}"
        local_profile = profiles["by_cep_prefix5_and_iptu_pattern"].get(cep_key)
        if local_profile and local_profile["count"] >= MIN_COMPARABLES:
            profile = local_profile
            scope_counts["cep_prefix5_and_iptu_pattern"] += 1
        else:
            profile = profiles["by_iptu_pattern_citywide"].get(pattern)
            scope_counts["iptu_pattern_citywide"] += 1
        if profile is None or profile["count"] < MIN_COMPARABLES:
            profile = profiles["citywide"]
            scope_counts["citywide"] += 1

        area = record["area"]
        prediction = float(profile["median_brl_per_m2"]) * area
        lower = float(profile["p10_brl_per_m2"]) * area
        upper = float(profile["p90_brl_per_m2"]) * area
        predictions.append(prediction)
        actuals.append(record["price"])
        range_hits += int(lower <= record["price"] <= upper)

    absolute_errors = [
        abs(actual - prediction)
        for actual, prediction in zip(actuals, predictions)
    ]
    absolute_percentage_errors = [
        error / actual for error, actual in zip(absolute_errors, actuals)
    ]
    ordered_apes = sorted(absolute_percentage_errors)
    mean_actual = sum(actuals) / len(actuals)
    total_sum_squares = sum((actual - mean_actual) ** 2 for actual in actuals)
    residual_sum_squares = sum(
        (actual - prediction) ** 2
        for actual, prediction in zip(actuals, predictions)
    )
    return {
        "method": (
            "Treino janeiro-junho de 2026; teste julho-setembro de 2026; "
            "transações do mesmo SQL no treino foram excluídas do teste."
        ),
        "training_transactions": len(training),
        "test_transactions": len(test),
        "mae_brl": round(sum(absolute_errors) / len(absolute_errors), 2),
        "median_absolute_percentage_error": round(
            ordered_apes[int((len(ordered_apes) - 1) * 0.50)], 6
        ),
        "p90_absolute_percentage_error": round(
            ordered_apes[int((len(ordered_apes) - 1) * 0.90)], 6
        ),
        "r2": round(
            1 - residual_sum_squares / total_sum_squares
            if total_sum_squares
            else 0,
            6,
        ),
        "p10_p90_range_coverage": round(range_hits / len(test), 6),
        "test_scope_counts": dict(scope_counts),
        "warning": (
            "Validação temporal retrospectiva na mesma base municipal, sem "
            "equivaler a validação independente de avaliação CAIXA."
        ),
    }


def build_reference_rates(data_dir: Path = DATA_DIR) -> dict[str, Any]:
    records, counts = _eligible_records(data_dir)
    dates = sorted(record["date"] for record in records)
    return {
        "schema_version": 1,
        "status": "experimental_not_for_operational_appraisal",
        "source_file": OFFICIAL_FILE,
        "source_sheet": OFFICIAL_SHEET,
        "target": (
            "Valor da transação declarado pelo contribuinte em compra e venda "
            "com transmissão integral (100%)."
        ),
        "area_basis": (
            "Área Construída (m2) do cadastro IPTU. Não é tratada como área "
            "privativa, área total ou área ocupada."
        ),
        "filter_counts": counts,
        "reference_period": {
            "start": dates[0],
            "end": dates[-1],
            "transactions": len(records),
        },
        "selection": {
            "transaction_nature": "1.Compra e venda",
            "sql_status": "Ativo Predial",
            "iptu_use_code": "20",
            "transferred_share_percent": 100,
            "built_area_m2_min": MIN_AREA_M2,
            "built_area_m2_max": MAX_AREA_M2,
            "iptu_pattern_codes": sorted(VALID_PATTERN_CODES),
            "ambiguous_composite_keys": "Excluded, not deduplicated",
            "target": "Declared ITBI transaction value, not fiscal value.",
        },
        "minimum_comparables": MIN_COMPARABLES,
        "profiles": _profiles(records),
        "temporal_backtest": _backtest(records),
        "limitations": [
            "A declared ITBI purchase price is not automatically a CAIXA appraisal value.",
            "The municipal dictionary defines built area as cadastral area and says it does not necessarily correspond to occupied area.",
            "Use the same IPTU built-area definition for input; do not substitute private or total area.",
            "IPTU pattern codes are treated as categorical codes, not as verified construction-quality ratings.",
            "The reference is limited to eligible São Paulo 2026 transactions through the latest source date.",
            "The p10-p90 range is an observed comparable-rate range, not a calibrated property-level confidence interval.",
            "No bedrooms, bathrooms, parking, elevator, condition, or other unsupported unit attributes are inferred.",
        ],
    }


def estimate_reference(
    reference: dict[str, Any],
    area_construida_iptu_m2: float,
    cep: str | None,
    iptu_pattern_code: str | None,
    confirm_area_basis: bool,
) -> dict[str, Any]:
    if not confirm_area_basis:
        raise ValueError(
            "Confirme que a área informada é Área Construída (m2) do cadastro IPTU; "
            "não use área privativa ou área total."
        )
    if not MIN_AREA_M2 <= area_construida_iptu_m2 <= MAX_AREA_M2:
        raise ValueError(
            f"A área de referência deve estar entre {MIN_AREA_M2:g} e "
            f"{MAX_AREA_M2:g} m²."
        )

    pattern = normalize_value(iptu_pattern_code, "number") if iptu_pattern_code else ""
    if pattern and pattern not in VALID_PATTERN_CODES:
        raise ValueError("Código Padrão (IPTU) deve estar entre 20 e 25.")
    cep_prefix = normalize_cep_prefix(cep) if cep else ""
    profiles = reference["profiles"]
    profile = None
    scope = ""
    if cep_prefix and pattern:
        local_key = f"{cep_prefix}|{pattern}"
        profile = profiles["by_cep_prefix5_and_iptu_pattern"].get(local_key)
        scope = "cep_prefix5_and_iptu_pattern"
    if profile is not None and profile["count"] < MIN_COMPARABLES:
        profile = None
    if profile is None and pattern:
        profile = profiles["by_iptu_pattern_citywide"].get(pattern)
        scope = "iptu_pattern_citywide"
    if profile is None and cep_prefix:
        profile = profiles.get("by_cep_prefix5", {}).get(cep_prefix)
        scope = "cep_prefix5"
        if profile is not None and profile["count"] < MIN_COMPARABLES:
            profile = None
    if profile is None or profile["count"] < MIN_COMPARABLES:
        profile = profiles["citywide"]
        scope = "citywide"

    area = float(area_construida_iptu_m2)
    median_rate = float(profile["median_brl_per_m2"])
    return {
        "status": "experimental_not_for_operational_appraisal",
        "target": reference["target"],
        "estimated_value_brl": round(median_rate * area, 2),
        "observed_comparable_range_brl": {
            "p10": round(float(profile["p10_brl_per_m2"]) * area, 2),
            "p90": round(float(profile["p90_brl_per_m2"]) * area, 2),
            "interpretation": (
                "Faixa p10-p90 das razões de preço por m² dos comparáveis; "
                "não é intervalo de confiança individual."
            ),
        },
        "median_comparable_rate_brl_per_m2": round(median_rate, 2),
        "area_basis": reference["area_basis"],
        "input": {
            "area_construida_iptu_m2": area,
            "cep_prefix5": cep_prefix or None,
            "iptu_pattern_code": pattern or None,
        },
        "comparable_support": {
            "scope": scope,
            "transactions": profile["count"],
            "minimum_required": MIN_COMPARABLES,
        },
        "reference_period": reference["reference_period"],
        "temporal_backtest": reference["temporal_backtest"],
        "warnings": [
            "Uso exclusivo para análise exploratória; não é valor de avaliação ou oferta.",
            "Não utilizar em decisão de crédito, garantia, compra/venda ou laudo CAIXA.",
            "A área deve usar a mesma definição cadastral IPTU; CEP e código IPTU são opcionais e apenas segmentam os comparáveis quando disponíveis.",
            "A validação temporal observou erro percentual absoluto mediano elevado e não substitui validação independente.",
        ],
    }


def _write_reference(output_path: Path, reference: dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(reference, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--estimate-area-iptu", type=float)
    parser.add_argument("--cep", help="CEP completo ou prefixo com 5 dígitos.")
    parser.add_argument("--iptu-pattern", help="Código Padrão (IPTU), de 20 a 25.")
    parser.add_argument(
        "--confirm-area-iptu",
        action="store_true",
        help="Confirma que a área é Área Construída cadastral IPTU, não privativa.",
    )
    args = parser.parse_args()

    reference = build_reference_rates(args.data_dir)
    _write_reference(args.output, reference)
    print(f"Referência experimental gerada: {args.output}")
    print(
        f"{reference['reference_period']['transactions']} transações elegíveis; "
        f"última data {reference['reference_period']['end']}."
    )
    if args.estimate_area_iptu is not None:
        if not args.iptu_pattern:
            raise ValueError("--iptu-pattern é obrigatório para estimar.")
        estimate = estimate_reference(
            reference,
            args.estimate_area_iptu,
            args.cep,
            args.iptu_pattern,
            args.confirm_area_iptu,
        )
        print(json.dumps(estimate, ensure_ascii=False, indent=2))
    elif args.cep or args.iptu_pattern or args.confirm_area_iptu:
        raise ValueError("--cep, --iptu-pattern e --confirm-area-iptu exigem --estimate-area-iptu.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError) as error:
        print(f"ERRO: {error}", file=sys.stderr)
        raise SystemExit(1) from error
