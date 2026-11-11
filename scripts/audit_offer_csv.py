"""Audit an authorized property-listing CSV without scraping or changing it."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = BASE_DIR / "dados" / "derivados" / "ofertas_imoveis_template.csv"
DEFAULT_REPORT = BASE_DIR / "dados" / "derivados" / "ofertas_auditoria.json"

REQUIRED_COLUMNS = {
    "listing_id",
    "source_name",
    "source_listing_id",
    "source_url",
    "source_license_or_permission",
    "listing_captured_at",
    "offer_status",
    "property_type",
    "asking_price_brl",
    "asking_price_evidence_ref",
    "asking_price_value_type",
    "area_value_m2",
    "area_type",
    "area_evidence_ref",
    "area_value_type",
}
VALID_PERMISSIONS = {"owned", "licensed", "authorized", "public_domain"}
VALID_STATUSES = {"active", "withdrawn", "sold", "rented", "unknown"}
VALID_AREA_TYPES = {"private", "built", "total", "usable", "unknown"}
VALID_EVIDENCE_TYPES = {"observed", "extracted", "calculated", "estimated", "missing"}
ATTRIBUTE_EVIDENCE_FIELDS = {
    "bedrooms": "bedrooms_evidence_ref",
    "bathrooms": "bathrooms_evidence_ref",
    "parking_spaces": "parking_evidence_ref",
    "condition_category": "condition_evidence_ref",
}


def _parse_date(value: str) -> date | None:
    value = value.strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None


def _number(value: str) -> float | None:
    value = value.strip()
    if not value:
        return None
    try:
        result = float(value.replace(",", "."))
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def audit_csv(input_path: Path) -> dict[str, object]:
    if not input_path.is_file():
        raise FileNotFoundError(f"CSV não encontrado: {input_path}")

    errors: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    counts: Counter[str] = Counter()
    header_columns: list[str] = []
    seen_listing_ids: Counter[str] = Counter()
    seen_content_keys: Counter[tuple[str, str, str, str]] = Counter()
    eligible_ids: set[str] = set()
    record_count = 0

    with input_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header_columns = reader.fieldnames or []
        missing_columns = sorted(REQUIRED_COLUMNS - set(header_columns))
        if missing_columns:
            return {
                "input_file": input_path.name,
                "row_count": 0,
                "required_columns_missing": missing_columns,
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
            }

        for row_number, row in enumerate(reader, start=2):
            if not any((value or "").strip() for value in row.values()):
                continue
            record_count += 1
            counts["records"] += 1
            row_errors: list[str] = []
            listing_id = (row.get("listing_id") or "").strip()
            source_id = (row.get("source_listing_id") or "").strip()
            permission = (row.get("source_license_or_permission") or "").strip().casefold()
            status = (row.get("offer_status") or "").strip().casefold()
            property_type = (row.get("property_type") or "").strip().casefold()
            captured_at = _parse_date(row.get("listing_captured_at") or "")
            price = _number(row.get("asking_price_brl") or "")
            area = _number(row.get("area_value_m2") or "")
            area_type = (row.get("area_type") or "").strip().casefold()

            if not listing_id:
                row_errors.append("missing_listing_id")
            else:
                seen_listing_ids[listing_id] += 1
            if not source_id:
                row_errors.append("missing_source_listing_id")
            if not (row.get("source_name") or "").strip():
                row_errors.append("missing_source_name")
            if not (row.get("source_url") or "").strip():
                row_errors.append("missing_source_url")
            if permission not in VALID_PERMISSIONS:
                row_errors.append("source_permission_not_confirmed")
            if not captured_at:
                row_errors.append("invalid_or_missing_capture_date")
            if status not in VALID_STATUSES or status == "unknown":
                row_errors.append("invalid_or_unknown_offer_status")
            if property_type not in {"apartment", "apartamento"}:
                row_errors.append("unsupported_or_missing_property_type")
            if price is None or price <= 0:
                row_errors.append("invalid_or_missing_asking_price")
            if not (row.get("asking_price_evidence_ref") or "").strip():
                row_errors.append("missing_asking_price_evidence_reference")
            price_type = (row.get("asking_price_value_type") or "").strip().casefold()
            if price_type not in {"observed", "extracted"}:
                row_errors.append("asking_price_not_observed_or_extracted")
            if area is None or not 10 <= area <= 2000:
                row_errors.append("invalid_or_out_of_range_area")
            if area_type not in VALID_AREA_TYPES or area_type == "unknown":
                row_errors.append("area_definition_not_confirmed")
            if not (row.get("area_evidence_ref") or "").strip():
                row_errors.append("missing_area_evidence_reference")
            area_value_type = (row.get("area_value_type") or "").strip().casefold()
            if area_value_type not in {"observed", "extracted"}:
                row_errors.append("area_not_observed_or_extracted")

            if status in {"sold", "rented"}:
                counts[f"status_{status}"] += 1
            else:
                counts[f"status_{status or 'missing'}"] += 1
            counts[f"permission_{permission or 'missing'}"] += 1
            counts[f"area_type_{area_type or 'missing'}"] += 1

            for attribute, evidence_field in ATTRIBUTE_EVIDENCE_FIELDS.items():
                value = (row.get(attribute) or "").strip()
                evidence = (row.get(evidence_field) or "").strip()
                value_type = (
                    row.get(f"{attribute}_value_type") or ""
                ).strip().casefold()
                if value and not evidence:
                    warnings.append(
                        {
                            "row": row_number,
                            "code": "attribute_value_without_evidence_reference",
                            "field": attribute,
                        }
                    )
                if value and value_type not in VALID_EVIDENCE_TYPES - {"missing"}:
                    warnings.append(
                        {
                            "row": row_number,
                            "code": "attribute_value_type_missing_or_invalid",
                            "field": attribute,
                        }
                    )

            if listing_id and price is not None and area is not None:
                listing_key = (
                    _normalize_text(row.get("source_name") or ""),
                    _normalize_text(source_id),
                    f"{price:.2f}",
                    f"{area:.2f}",
                )
                seen_content_keys[listing_key] += 1

            if row_errors:
                errors.append(
                    {"row": row_number, "listing_id": listing_id, "codes": row_errors}
                )
            else:
                eligible_ids.add(listing_id)
                counts["rows_passing_basic_checks"] += 1

    duplicate_id_groups = sum(count > 1 for count in seen_listing_ids.values())
    duplicate_content_groups = sum(count > 1 for count in seen_content_keys.values())
    if duplicate_id_groups:
        warnings.append(
            {
                "code": "duplicate_listing_ids",
                "groups": duplicate_id_groups,
                "rows_in_duplicate_groups": sum(
                    count for count in seen_listing_ids.values() if count > 1
                ),
            }
        )
    if duplicate_content_groups:
        warnings.append(
            {
                "code": "possible_duplicate_listing_content",
                "groups": duplicate_content_groups,
                "match_fields": [
                    "source_name",
                    "source_listing_id",
                    "asking_price_brl",
                    "area_value_m2",
                ],
            }
        )

    duplicate_listing_ids = {
        listing_id for listing_id, count in seen_listing_ids.items() if count > 1
    }
    eligible_unique_ids = eligible_ids - duplicate_listing_ids
    counts["unique_listing_ids"] = len(seen_listing_ids)
    counts["duplicate_listing_id_groups"] = duplicate_id_groups
    counts["possible_duplicate_content_groups"] = duplicate_content_groups
    counts["unique_rows_passing_basic_checks"] = len(eligible_unique_ids)

    return {
        "input_file": input_path.name,
        "row_count": record_count,
        "required_columns_missing": [],
        "training_ready": False,
        "initial_screening_passed": (
            bool(record_count)
            and not errors
            and not warnings
            and duplicate_id_groups == 0
        ),
        "training_block_reason": (
            "A auditoria sintática não comprova licença, identidade da unidade, "
            "representatividade, deduplicação externa nem validação do modelo."
        ),
        "unique_rows_passing_basic_checks": len(eligible_unique_ids),
        "target_definition": (
            "asking_price_brl at listing_captured_at; advertised price only"
        ),
        "counts": dict(sorted(counts.items())),
        "errors": errors,
        "warnings": warnings,
        "limitations": [
            "Checks do not prove source license, truthfulness, or property-unit identity.",
            "Rows passing checks are not automatically suitable for model training.",
            "A model trained on listings predicts asking prices, not sale prices or appraisals.",
            "Training additionally needs deduplication, temporal/geographic validation, and leakage review.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audita CSV de anúncios autorizados; não coleta nem treina modelo."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args(argv)

    report = audit_csv(args.input)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"CSV auditado: {args.input}; linhas={report['row_count']}; "
        f"triagem_inicial={report['initial_screening_passed']}; "
        f"treino_liberado={report['training_ready']}; "
        f"relatório={args.report}"
    )
    return 0 if not report.get("required_columns_missing") else 2


if __name__ == "__main__":
    sys.exit(main())
