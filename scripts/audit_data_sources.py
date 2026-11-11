"""Audit joins between the enriched workbook and the PMSP ITBI workbook."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterator
from zipfile import BadZipFile, ZipFile


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "dados"
OFFICIAL_FILE = "1. APARTAMENTOS.xlsx"
ENRICHED_FILE = "22.10.2026.xlsx"
OFFICIAL_SHEET = "2026"
ENRICHED_SHEET = "9662 DADOS"
REFERENCE_YEAR = 2026

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"main": MAIN_NS, "rel": REL_NS}

JOIN_FIELDS = (
    ("sql", "N° do Cadastro (SQL)", "N° do Cadastro (SQL)", "text"),
    ("transaction_date", "Data de Transação", "Data de Transação", "number"),
    (
        "declared_transaction_value",
        "Valor de Transação (declarado pelo contribuinte)",
        "Valor de Transação (declarado pelo contribuinte)",
        "number",
    ),
)

FIELD_COMPARISONS = (
    ("sql", "N° do Cadastro (SQL)", "N° do Cadastro (SQL)", "text"),
    ("registration", "Matrícula do Imóvel", "Matrícula do Imóvel", "text"),
    ("declared_transaction_value", "Valor de Transação (declarado pelo contribuinte)", "Valor de Transação (declarado pelo contribuinte)", "number"),
    ("reference_tax_value", "Valor Venal de Referência", "Valor Venal de Referência", "number"),
    ("land_area_m2", "Área do Terreno (m2)", "Área do Terreno (m2)", "number"),
    ("frontage_m", "Testada (m)", "Testada (m)", "number"),
    ("ideal_fraction", "Fração Ideal", "Fração Ideal", "number"),
    ("construction_year_acc", "ACC (IPTU)", "ACC (IPTU)", "number"),
    ("property_tax_pattern", "Padrão (IPTU)", "Padrão (IPTU)", "number"),
)

OFFICIAL_FIELDS_TO_PROFILE = (
    "N° do Cadastro (SQL)",
    "CEP",
    "Data de Transação",
    "Valor de Transação (declarado pelo contribuinte)",
    "Valor Venal de Referência",
    "Área do Terreno (m2)",
    "Testada (m)",
    "Fração Ideal",
    "Área Construída (m2)",
    "Uso (IPTU)",
    "Padrão (IPTU)",
    "ACC (IPTU)",
)
ENRICHED_FIELDS_TO_PROFILE = (
    "N° do Cadastro (SQL)",
    "Data de Transação",
    "Valor de Transação (declarado pelo contribuinte)",
    "IDADE",
    "QUARTOS",
    "BANHEIROS",
    "VAGAS",
    "ELEVADOR",
    "Área total",
    "ÁREA PRIVATIVA (m²)",
)


def normalize_value(value: object, kind: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if kind == "text":
        return text.lstrip("0") or "0"

    try:
        number = Decimal(text.replace(",", "."))
    except InvalidOperation:
        return text
    if not number.is_finite():
        return ""
    return format(number.normalize(), "f")


def _canonical_cell(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        number = Decimal(text.replace(",", "."))
    except InvalidOperation:
        return text
    return format(number.normalize(), "f") if number.is_finite() else ""


def excel_column_index(cell_reference: str) -> int:
    match = re.match(r"[A-Z]+", cell_reference)
    if not match:
        raise ValueError(f"Referência de célula inválida: {cell_reference}")

    index = 0
    for character in match.group():
        index = index * 26 + ord(character) - ord("A") + 1
    return index - 1


def _read_shared_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return [
        "".join(text.text or "" for text in item.findall(".//main:t", NS))
        for item in root.findall("main:si", NS)
    ]


def _worksheet_path(archive: ZipFile, sheet_name: str | None) -> str:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {
        relationship.attrib["Id"]: relationship.attrib["Target"]
        for relationship in relationships.findall(f"{{{PKG_REL_NS}}}Relationship")
    }

    sheets = workbook.findall("main:sheets/main:sheet", NS)
    selected = next(
        (sheet for sheet in sheets if sheet_name is None or sheet.attrib["name"] == sheet_name),
        None,
    )
    if selected is None:
        requested = sheet_name or "first worksheet"
        raise ValueError(f"Planilha não encontrada: {requested}")

    target = targets[selected.attrib[f"{{{REL_NS}}}id"]].lstrip("/")
    return target if target.startswith("xl/") else f"xl/{target}"


def iter_xlsx_rows(
    path: Path,
    sheet_name: str | None = None,
    include_source_row: bool = False,
) -> Iterator[dict[str, str]]:
    """Read worksheet values using only the Python standard library."""
    with ZipFile(path) as archive:
        shared_strings = _read_shared_strings(archive)
        worksheet_path = _worksheet_path(archive, sheet_name)
        with archive.open(worksheet_path) as worksheet:
            rows = ET.iterparse(worksheet, events=("end",))
            headers: list[str] | None = None

            for _, row in rows:
                if row.tag != f"{{{MAIN_NS}}}row":
                    continue

                cells: dict[int, str] = {}
                for cell in row.findall(f"{{{MAIN_NS}}}c"):
                    index = excel_column_index(cell.attrib.get("r", ""))
                    value = cell.find(f"{{{MAIN_NS}}}v")
                    cell_value = value.text if value is not None and value.text else ""

                    cell_type = cell.attrib.get("t")
                    if cell_type == "s" and cell_value:
                        cell_value = shared_strings[int(cell_value)]
                    elif cell_type == "inlineStr":
                        cell_value = "".join(
                            text.text or ""
                            for text in cell.findall(".//main:t", NS)
                        )
                    cells[index] = cell_value

                if headers is None:
                    if not cells:
                        row.clear()
                        continue
                    headers = [
                        cells.get(index, "").strip()
                        for index in range(max(cells) + 1)
                    ]
                elif any(value.strip() for value in cells.values()):
                    values = {
                        headers[index]: value
                        for index, value in cells.items()
                        if index < len(headers) and headers[index]
                    }
                    if include_source_row:
                        values["_source_excel_row"] = row.attrib.get("r", "")
                    yield values

                row.clear()


def _transaction_key(row: dict[str, str]) -> tuple[str, ...]:
    return tuple(
        normalize_value(row.get(source_field, ""), kind)
        for _, source_field, _, kind in JOIN_FIELDS
    )


def _excel_serial_date(value: str) -> str | None:
    normalized = normalize_value(value, "number")
    if not normalized:
        return None
    try:
        serial = Decimal(normalized)
    except InvalidOperation:
        return None
    if serial != serial.to_integral_value():
        return None
    return (datetime(1899, 12, 30) + timedelta(days=int(serial))).date().isoformat()


def audit_workbooks(data_dir: Path = DATA_DIR) -> dict[str, object]:
    official_path = data_dir / OFFICIAL_FILE
    enriched_path = data_dir / ENRICHED_FILE
    for path in (official_path, enriched_path):
        if not path.is_file():
            raise FileNotFoundError(f"Arquivo necessário não encontrado: {path}")

    official_by_key: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    official_count = 0
    official_dates: list[str] = []
    official_field_presence = {field: 0 for field in OFFICIAL_FIELDS_TO_PROFILE}
    for row in iter_xlsx_rows(official_path, OFFICIAL_SHEET):
        official_count += 1
        for field in official_field_presence:
            if row.get(field, "").strip():
                official_field_presence[field] += 1
        key = _transaction_key(row)
        if all(key):
            official_by_key[key].append(row)
            date = _excel_serial_date(row.get("Data de Transação", ""))
            if date:
                official_dates.append(date)

    enriched_count = 0
    counts = {
        "matched_unique": 0,
        "matched_ambiguous": 0,
        "unmatched": 0,
        "age_matches_reference_year_minus_acc": 0,
        "age_comparable": 0,
        "private_area_not_greater_than_total": 0,
        "area_comparable": 0,
    }
    field_agreement = {
        field_id: {"comparable": 0, "equal": 0}
        for field_id, _, _, _ in FIELD_COMPARISONS
    }
    enriched_field_presence = {field: 0 for field in ENRICHED_FIELDS_TO_PROFILE}
    ambiguous_comparable_groups = 0
    ambiguous_consistent_groups = 0
    ambiguous_identical_source_groups = 0
    enriched_dates: list[str] = []

    for enriched in iter_xlsx_rows(enriched_path, ENRICHED_SHEET):
        enriched_count += 1
        for field in enriched_field_presence:
            if enriched.get(field, "").strip():
                enriched_field_presence[field] += 1
        key = tuple(
            normalize_value(enriched.get(enriched_field, ""), kind)
            for _, _, enriched_field, kind in JOIN_FIELDS
        )
        matches = official_by_key.get(key, []) if all(key) else []

        if not matches:
            counts["unmatched"] += 1
        elif len(matches) == 1:
            counts["matched_unique"] += 1
            official = matches[0]
            for field_id, enriched_field, official_field, kind in FIELD_COMPARISONS:
                left = normalize_value(enriched.get(enriched_field, ""), kind)
                right = normalize_value(official.get(official_field, ""), kind)
                if left and right:
                    field_agreement[field_id]["comparable"] += 1
                    if left == right:
                        field_agreement[field_id]["equal"] += 1
        else:
            counts["matched_ambiguous"] += 1
            source_rows = {
                tuple(
                    sorted(
                        (field, _canonical_cell(value))
                        for field, value in match.items()
                    )
                )
                for match in matches
            }
            if len(source_rows) == 1:
                ambiguous_identical_source_groups += 1

            official_fields = [
                (
                    field_id,
                    official_field,
                    kind,
                )
                for field_id, _, official_field, kind in FIELD_COMPARISONS
            ]
            comparable = [
                all(
                    normalize_value(match.get(field, ""), kind)
                    for _, field, kind in official_fields
                )
                for match in matches
            ]
            if any(comparable):
                ambiguous_comparable_groups += 1
                projections = {
                    tuple(
                        normalize_value(match.get(field, ""), kind)
                        for _, field, kind in official_fields
                    )
                    for match in matches
                }
                if len(projections) == 1:
                    ambiguous_consistent_groups += 1

        acc = normalize_value(enriched.get("ACC (IPTU)", ""), "number")
        age = normalize_value(enriched.get("IDADE", ""), "number")
        if acc and age:
            counts["age_comparable"] += 1
            try:
                if Decimal(age) == Decimal(REFERENCE_YEAR) - Decimal(acc):
                    counts["age_matches_reference_year_minus_acc"] += 1
            except InvalidOperation:
                pass

        private_area = normalize_value(enriched.get("ÁREA PRIVATIVA (m²)", ""), "number")
        total_area = normalize_value(enriched.get("Área total", ""), "number")
        if private_area and total_area:
            counts["area_comparable"] += 1
            if Decimal(private_area) <= Decimal(total_area):
                counts["private_area_not_greater_than_total"] += 1

        date = _excel_serial_date(enriched.get("Data de Transação", ""))
        if date:
            enriched_dates.append(date)

    duplicate_source_keys = sum(
        1 for matches in official_by_key.values() if len(matches) > 1
    )
    match_rate = (
        (counts["matched_unique"] + counts["matched_ambiguous"]) / enriched_count
        if enriched_count
        else 0
    )

    return {
        "audit_version": 1,
        "reference_year_for_age_check": REFERENCE_YEAR,
        "inputs": {
            "official_workbook": OFFICIAL_FILE,
            "official_rows": official_count,
            "enriched_workbook": ENRICHED_FILE,
            "enriched_rows": enriched_count,
        },
        "join": {
            "key_fields": [
                "SQL",
                "Data de Transação",
                "Valor de Transação (declarado pelo contribuinte)",
            ],
            "matched_unique_rows": counts["matched_unique"],
            "matched_ambiguous_rows": counts["matched_ambiguous"],
            "unmatched_rows": counts["unmatched"],
            "match_rate": round(match_rate, 6),
            "duplicate_source_key_groups": duplicate_source_keys,
            "ambiguous_groups_with_comparable_attributes": ambiguous_comparable_groups,
            "ambiguous_groups_consistent_on_compared_attributes": ambiguous_consistent_groups,
            "ambiguous_groups_identical_on_all_source_fields": ambiguous_identical_source_groups,
        },
        "field_agreement_for_unique_matches": {
            field_id: {
                **values,
                "agreement_rate": round(values["equal"] / values["comparable"], 6)
                if values["comparable"]
                else None,
            }
            for field_id, values in field_agreement.items()
        },
        "field_presence": {
            "official": {
                field: {
                    "nonempty": count,
                    "rows": official_count,
                    "rate": round(count / official_count, 6) if official_count else None,
                }
                for field, count in official_field_presence.items()
            },
            "enriched": {
                field: {
                    "nonempty": count,
                    "rows": enriched_count,
                    "rate": round(count / enriched_count, 6) if enriched_count else None,
                }
                for field, count in enriched_field_presence.items()
            },
        },
        "derived_field_checks": {
            "age_equals_reference_year_minus_acc": {
                "comparable": counts["age_comparable"],
                "equal": counts["age_matches_reference_year_minus_acc"],
                "agreement_rate": round(
                    counts["age_matches_reference_year_minus_acc"]
                    / counts["age_comparable"],
                    6,
                )
                if counts["age_comparable"]
                else None,
                "interpretation": (
                    "Confirma consistência aritmética, não comprova a semântica "
                    "de ACC nem a data de referência adotada na origem."
                ),
            },
            "private_area_not_greater_than_total": {
                "comparable": counts["area_comparable"],
                "passes": counts["private_area_not_greater_than_total"],
                "pass_rate": round(
                    counts["private_area_not_greater_than_total"]
                    / counts["area_comparable"],
                    6,
                )
                if counts["area_comparable"]
                else None,
            },
        },
        "transaction_date_range": {
            "enriched_min": min(enriched_dates) if enriched_dates else None,
            "enriched_max": max(enriched_dates) if enriched_dates else None,
            "official_min": min(official_dates) if official_dates else None,
            "official_max": max(official_dates) if official_dates else None,
        },
        "limitations": [
            "Chave composta idêntica comprova vínculo com um registro ITBI, não a conclusão ou representatividade de mercado da transação.",
            "A concordância entre planilhas não comprova a origem de quartos, banheiros, vagas, elevador ou áreas privativas.",
            "Grupos com chave duplicada permanecem ambíguos e não devem ser deduplicados automaticamente.",
            "ACC, área construída, área total e área privativa não são conceitos intercambiáveis.",
        ],
    }


def build_analysis_extract(data_dir: Path = DATA_DIR) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Return a traceable ITBI extract for unique matches only."""
    for filename in (OFFICIAL_FILE, ENRICHED_FILE):
        path = data_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"Arquivo necessário não encontrado: {path}")

    official_by_key: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for row in iter_xlsx_rows(
        data_dir / OFFICIAL_FILE, OFFICIAL_SHEET, include_source_row=True
    ):
        key = _transaction_key(row)
        if all(key):
            official_by_key[key].append(row)

    output_rows: list[dict[str, str]] = []
    counts = {"unique": 0, "ambiguous": 0, "unmatched": 0}
    for enriched in iter_xlsx_rows(data_dir / ENRICHED_FILE, ENRICHED_SHEET):
        key = tuple(
            normalize_value(enriched.get(enriched_field, ""), kind)
            for _, _, enriched_field, kind in JOIN_FIELDS
        )
        matches = official_by_key.get(key, []) if all(key) else []
        if not matches:
            counts["unmatched"] += 1
            continue
        if len(matches) != 1:
            counts["ambiguous"] += 1
            continue

        source = matches[0]
        key_digest = hashlib.sha256(
            "|".join(key).encode("utf-8")
        ).hexdigest()
        output_rows.append(
            {
                "record_key_sha256": key_digest,
                "match_status": "unique_sql_date_declared_value",
                "source_file": OFFICIAL_FILE,
                "source_sheet": OFFICIAL_SHEET,
                "source_excel_row": source.get("_source_excel_row", ""),
                "sql": source.get("N° do Cadastro (SQL)", ""),
                "postal_code": source.get("CEP", ""),
                "transaction_date": _excel_serial_date(
                    source.get("Data de Transação", "")
                )
                or source.get("Data de Transação", ""),
                "price_type": "itbi_value_declared_by_taxpayer",
                "declared_transaction_value_brl": source.get(
                    "Valor de Transação (declarado pelo contribuinte)", ""
                ),
                "reference_tax_value_brl": source.get("Valor Venal de Referência", ""),
                "reference_tax_value_proportional_brl": source.get(
                    "Valor Venal de Referência (proporcional)", ""
                ),
                "tax_base_value_brl": source.get("Base de Cálculo adotada", ""),
                "transferred_share_percent": source.get(
                    "Proporção Transmitida (%)", ""
                ),
                "land_area_cadastral_m2": source.get("Área do Terreno (m2)", ""),
                "frontage_m": source.get("Testada (m)", ""),
                "ideal_fraction": source.get("Fração Ideal", ""),
                "built_area_iptu_m2": source.get("Área Construída (m2)", ""),
                "use_iptu_code": source.get("Uso (IPTU)", ""),
                "use_iptu_description": source.get("Descrição do uso (IPTU)", ""),
                "construction_pattern_iptu_code": source.get("Padrão (IPTU)", ""),
                "construction_pattern_iptu_description": source.get(
                    "Descrição do padrão (IPTU)", ""
                ),
                "acc_iptu_source_raw": source.get("ACC (IPTU)", ""),
                "source_notes": (
                    "Atributos da planilha enriquecida sem proveniência não foram "
                    "incluídos; área cadastral não equivale a área privativa."
                ),
            }
        )
        counts["unique"] += 1

    return output_rows, counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument(
        "--output",
        type=Path,
        help="Grava o JSON neste caminho; sem esta opção, imprime no stdout.",
    )
    parser.add_argument(
        "--export-analysis-csv",
        type=Path,
        help="Exporta apenas ligações ITBI únicas para uma tabela de análise, não operacional.",
    )
    args = parser.parse_args()

    report = audit_workbooks(args.data_dir)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
        print(f"Relatório salvo: {args.output}")
    else:
        print(rendered)

    if args.export_analysis_csv:
        extract, counts = build_analysis_extract(args.data_dir)
        args.export_analysis_csv.parent.mkdir(parents=True, exist_ok=True)
        if extract:
            with args.export_analysis_csv.open(
                "w", encoding="utf-8-sig", newline=""
            ) as output:
                writer = csv.DictWriter(output, fieldnames=list(extract[0]))
                writer.writeheader()
                writer.writerows(extract)
        else:
            raise ValueError("Nenhum vínculo único disponível para exportação.")
        print(
            "Tabela de análise salva: "
            f"{args.export_analysis_csv} "
            f"({counts['unique']} únicos; {counts['ambiguous']} ambíguos excluídos; "
            f"{counts['unmatched']} sem vínculo)"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, BadZipFile) as error:
        print(f"ERRO: {error}", file=sys.stderr)
        raise SystemExit(1) from error
