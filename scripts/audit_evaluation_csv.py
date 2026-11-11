"""Audit authorized appraisal labels without enabling training automatically."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = BASE_DIR / "dados" / "derivados" / "avaliacoes_imoveis_template.csv"
DEFAULT_REPORT = BASE_DIR / "dados" / "derivados" / "avaliacoes_auditoria.json"

REQUIRED_COLUMNS = {
    "valuation_record_id",
    "property_token",
    "valuation_value_brl",
    "valuation_date",
    "valuation_purpose",
    "value_basis",
    "valuation_method",
    "appraisal_status",
    "property_type",
    "city",
    "state",
    "unit_match_status",
    "area_value_m2",
    "area_type",
    "area_source",
    "area_evidence_ref",
    "target_document_ref",
    "target_document_sha256",
    "source_permission",
    "review_status",
}
VALID_AREA_TYPES = {"private", "built", "total"}
VALID_PERMISSIONS = {"owned", "licensed", "authorized", "public_domain"}
VALID_APPRAISAL_STATUSES = {"final", "reviewed_final"}
VALID_REVIEW_STATUSES = {"reviewed", "approved"}
VALID_VALUE_TYPES = {"observed", "extracted", "calculated", "estimated", "missing"}
VALID_ENTITY_SCOPES = {"unit", "building"}
OPTIONAL_FEATURES = {
    "bedrooms": "unit",
    "bathrooms": "unit",
    "parking_spaces": "unit",
    "elevator": "building",
    "building_year": "building",
}


def _number(value: str | None) -> float | None:
    if not value:
        return None
    try:
        parsed = float(value.strip().replace(",", "."))
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def _is_date(value: str | None) -> bool:
    if not value:
        return False
    try:
        date.fromisoformat(value.strip()[:10])
    except ValueError:
        return False
    return True


def _normal(value: str | None) -> str:
    return (value or "").strip().casefold()


def audit_csv(input_path: Path) -> dict[str, object]:
    if not input_path.is_file():
        raise FileNotFoundError(f"CSV não encontrado: {input_path}")

    errors: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    counts: Counter[str] = Counter()
    ids: Counter[str] = Counter()
    property_records: dict[str, set[str]] = defaultdict(set)
    feature_coverage: Counter[str] = Counter()
    row_count = 0
    candidates = 0

    with input_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        missing_columns = sorted(REQUIRED_COLUMNS - set(fields))
        if missing_columns:
            return {
                "input_file": input_path.name,
                "row_count": 0,
                "required_columns_missing": missing_columns,
                "candidate_rows_for_expert_review": 0,
                "training_ready": False,
                "errors": [
                    {
                        "row": 1,
                        "code": "missing_required_columns",
                        "fields": missing_columns,
                    }
                ],
                "warnings": [],
                "counts": {},
                "feature_evidence_coverage": {},
            }

        for row_number, raw_row in enumerate(reader, start=2):
            row = {key: value or "" for key, value in raw_row.items() if key}
            if not any(value.strip() for value in row.values()):
                continue
            row_count += 1
            row_errors: list[str] = []

            record_id = row.get("valuation_record_id", "").strip()
            property_token = row.get("property_token", "").strip()
            value = _number(row.get("valuation_value_brl"))
            area = _number(row.get("area_value_m2"))
            value_basis = _normal(row.get("value_basis"))
            permission = _normal(row.get("source_permission"))
            appraisal_status = _normal(row.get("appraisal_status"))
            review_status = _normal(row.get("review_status"))
            area_type = _normal(row.get("area_type"))
            sha256 = row.get("target_document_sha256", "").strip().casefold()

            if not record_id:
                row_errors.append("missing_valuation_record_id")
            else:
                ids[record_id] += 1
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", property_token.casefold()):
                row_errors.append("property_token_must_be_sha256_pseudonym")
            else:
                property_records[property_token].add(record_id)
            if value is None or value <= 0:
                row_errors.append("invalid_or_missing_valuation_value")
            if not _is_date(row.get("valuation_date")):
                row_errors.append("invalid_or_missing_valuation_date")
            if not row.get("valuation_purpose", "").strip():
                row_errors.append("missing_valuation_purpose")
            if value_basis not in {"market_value", "valor_de_mercado"}:
                row_errors.append("valuation_basis_not_market_value")
            if not row.get("valuation_method", "").strip():
                row_errors.append("missing_valuation_method")
            if appraisal_status not in VALID_APPRAISAL_STATUSES:
                row_errors.append("appraisal_not_final")
            if _normal(row.get("property_type")) not in {"apartment", "apartamento"}:
                row_errors.append("unsupported_property_type")
            if _normal(row.get("city")) not in {"sao paulo", "são paulo"} or _normal(
                row.get("state")
            ) != "sp":
                row_errors.append("outside_model_geography")
            if _normal(row.get("unit_match_status")) != "confirmed":
                row_errors.append("appraised_unit_identity_not_confirmed")
            if area is None or not 10 <= area <= 2000:
                row_errors.append("invalid_or_out_of_range_area")
            if area_type not in VALID_AREA_TYPES:
                row_errors.append("area_definition_not_confirmed")
            if not row.get("area_source", "").strip() or not row.get(
                "area_evidence_ref", ""
            ).strip():
                row_errors.append("missing_area_provenance")
            if not row.get("target_document_ref", "").strip():
                row_errors.append("missing_target_document_reference")
            if not re.fullmatch(r"[0-9a-f]{64}", sha256):
                row_errors.append("invalid_or_missing_target_document_sha256")
            if permission not in VALID_PERMISSIONS:
                row_errors.append("source_permission_not_confirmed")
            if review_status not in VALID_REVIEW_STATUSES:
                row_errors.append("target_not_independently_reviewed")

            for feature, required_scope in OPTIONAL_FEATURES.items():
                feature_value = row.get(feature, "").strip()
                evidence = row.get(f"{feature}_evidence_ref", "").strip()
                value_type = _normal(row.get(f"{feature}_value_type"))
                scope = _normal(row.get(f"{feature}_entity_scope"))
                if feature_value:
                    if evidence and value_type in VALID_VALUE_TYPES - {"missing"}:
                        feature_coverage[f"{feature}_with_evidence"] += 1
                    else:
                        warnings.append(
                            {
                                "row": row_number,
                                "code": "feature_without_complete_evidence",
                                "field": feature,
                            }
                        )
                    if scope != required_scope:
                        warnings.append(
                            {
                                "row": row_number,
                                "code": "feature_entity_scope_mismatch",
                                "field": feature,
                                "expected": required_scope,
                            }
                        )

            if not row_errors:
                candidates += 1
            else:
                errors.append(
                    {"row": row_number, "codes": row_errors}
                )

        duplicate_ids = sorted(record_id for record_id, count in ids.items() if count > 1)
        counts["duplicate_valuation_record_id_groups"] = len(duplicate_ids)
        if duplicate_ids:
            errors.append(
                {
                    "row": None,
                    "code": "duplicate_valuation_record_ids",
                    "duplicate_groups": len(duplicate_ids),
                }
            )

    repeated_properties = {
        token: sorted(records)
        for token, records in property_records.items()
        if len(records) > 1
    }
    if repeated_properties:
        warnings.append(
            {
                "code": "repeated_properties_must_stay_in_same_validation_fold",
                "property_groups": len(repeated_properties),
            }
        )

    counts["rows_with_validated_feature_evidence"] = sum(
        feature_coverage.values()
    )
    counts["unique_property_tokens"] = len(property_records)
    counts["repeated_property_groups"] = len(repeated_properties)
    return {
        "input_file": input_path.name,
        "target_definition": (
            "final reviewed market-value appraisal in BRL at valuation_date"
        ),
        "row_count": row_count,
        "candidate_rows_for_expert_review": candidates if not duplicate_ids else 0,
        "unique_property_tokens": len(property_records),
        "repeated_property_groups": len(repeated_properties),
        "training_ready": False,
        "training_block_reason": (
            "A aprovação técnica, a suficiência/representatividade da amostra, "
            "a validação independente e a compatibilidade operacional não são "
            "decididas por esta auditoria sintática."
        ),
        "errors": errors,
        "warnings": warnings,
        "counts": dict(counts),
        "feature_evidence_coverage": {
            feature: {
                "rows_with_evidence": feature_coverage.get(
                    f"{feature}_with_evidence", 0
                ),
                "coverage_percent_of_all_rows": round(
                    feature_coverage.get(f"{feature}_with_evidence", 0)
                    / row_count
                    * 100,
                    2,
                )
                if row_count
                else 0,
            }
            for feature in OPTIONAL_FEATURES
        },
        "warnings_about_sampling": [
            "Não há mínimo universal de observações codificado; os responsáveis devem justificar escopo e representatividade.",
            "Separar treino/teste por property_token para evitar que avaliações da mesma unidade vazem entre partições.",
            "Usar partição temporal quando a data-base e o volume permitirem; relatar métricas somente para o alvo de avaliação.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    report = audit_csv(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["row_count"] > 0 and not report["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
