import tempfile
import unittest
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from scripts.audit_data_sources import (
    DATA_DIR,
    audit_workbooks,
    build_analysis_extract,
    excel_column_index,
    iter_xlsx_rows,
    normalize_value,
)


def write_minimal_workbook(path: Path):
    workbook = """<?xml version="1.0" encoding="UTF-8"?>
    <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
      xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
      <sheets><sheet name="Dados" sheetId="1" r:id="rId1"/></sheets>
    </workbook>"""
    relationships = """<?xml version="1.0" encoding="UTF-8"?>
    <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rId1" Target="worksheets/sheet1.xml"
        Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/>
    </Relationships>"""
    shared_strings = """<?xml version="1.0" encoding="UTF-8"?>
    <sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="2" uniqueCount="2">
      <si><t>SQL</t></si><si><t>Valor</t></si>
    </sst>"""
    worksheet = """<?xml version="1.0" encoding="UTF-8"?>
    <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
      <sheetData>
        <row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>
        <row r="2"><c r="A2" t="inlineStr"><is><t>000123</t></is></c><c r="B2"><v>10.00</v></c></row>
      </sheetData>
    </worksheet>"""
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relationships)
        archive.writestr("xl/sharedStrings.xml", shared_strings)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)


class DataAuditTests(unittest.TestCase):
    def test_normalizes_decimal_and_sql_keys(self):
        self.assertEqual(normalize_value("00123.000", "number"), "123")
        self.assertEqual(normalize_value("000123", "text"), "123")
        self.assertEqual(normalize_value("  ", "number"), "")

    def test_converts_excel_column_names_to_zero_based_indexes(self):
        self.assertEqual(excel_column_index("A1"), 0)
        self.assertEqual(excel_column_index("Z7"), 25)
        self.assertEqual(excel_column_index("AA9"), 26)

    def test_reads_shared_and_inline_strings_from_xlsx(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            workbook_path = Path(temporary_dir) / "sample.xlsx"
            write_minimal_workbook(workbook_path)
            rows = list(iter_xlsx_rows(workbook_path, sheet_name="Dados"))
            rows_with_source = list(
                iter_xlsx_rows(
                    workbook_path, sheet_name="Dados", include_source_row=True
                )
            )

        self.assertEqual(rows, [{"SQL": "000123", "Valor": "10.00"}])
        self.assertEqual(
            rows_with_source,
            [{"SQL": "000123", "Valor": "10.00", "_source_excel_row": "2"}],
        )

    @unittest.skipUnless(
        (DATA_DIR / "1. APARTAMENTOS.xlsx").is_file()
        and (DATA_DIR / "22.10.2026.xlsx").is_file(),
        "Source workbooks are not present in this checkout.",
    )
    def test_local_enriched_rows_match_official_itbi_transactions(self):
        report = audit_workbooks(DATA_DIR)
        join = report["join"]
        self.assertEqual(join["matched_unique_rows"], 9658)
        self.assertEqual(join["matched_ambiguous_rows"], 2)
        self.assertEqual(join["unmatched_rows"], 0)
        self.assertEqual(join["match_rate"], 1.0)
        self.assertEqual(
            join["ambiguous_groups_consistent_on_compared_attributes"], 2
        )
        self.assertEqual(
            report["derived_field_checks"]["age_equals_reference_year_minus_acc"][
                "agreement_rate"
            ],
            1.0,
        )
        self.assertEqual(
            report["field_agreement_for_unique_matches"]["construction_year_acc"][
                "equal"
            ],
            9607,
        )
        extract, counts = build_analysis_extract(DATA_DIR)
        self.assertEqual(counts, {"unique": 9658, "ambiguous": 2, "unmatched": 0})
        self.assertEqual(len(extract), 9658)
        self.assertEqual(extract[0]["price_type"], "itbi_value_declared_by_taxpayer")
        self.assertIn("source_excel_row", extract[0])
        self.assertIn("postal_code", extract[0])
        self.assertNotIn("bedrooms", extract[0])


if __name__ == "__main__":
    unittest.main()
