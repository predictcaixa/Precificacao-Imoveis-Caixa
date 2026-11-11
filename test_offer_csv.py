from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from scripts.audit_offer_csv import audit_csv


TEMPLATE = (
    Path(__file__).resolve().parent
    / "dados"
    / "derivados"
    / "ofertas_imoveis_template.csv"
)


def sample_listing() -> dict[str, str]:
    with TEMPLATE.open(encoding="utf-8-sig", newline="") as handle:
        fields = next(csv.reader(handle))
    row = {field: "" for field in fields}
    row.update(
        {
            "listing_id": "sha256:listing-snapshot-001",
            "source_name": "authorized_sample_source",
            "source_listing_id": "listing-001",
            "source_url": "https://example.invalid/listing-001",
            "source_license_or_permission": "licensed",
            "listing_captured_at": "2026-08-01T12:00:00-03:00",
            "offer_status": "active",
            "property_type": "apartment",
            "city": "São Paulo",
            "state": "SP",
            "asking_price_brl": "650000",
            "asking_price_evidence_ref": "listing-001#price",
            "asking_price_value_type": "extracted",
            "price_currency": "BRL",
            "area_value_m2": "75",
            "area_type": "private",
            "area_evidence_ref": "listing-001#area",
            "area_value_type": "extracted",
            "bedrooms": "2",
            "bedrooms_evidence_ref": "listing-001#bedrooms",
            "bedrooms_value_type": "extracted",
        }
    )
    return row


class OfferCsvAuditTests(unittest.TestCase):
    def write_csv(self, directory: str, rows: list[dict[str, str]]) -> Path:
        path = Path(directory) / "listings.csv"
        with TEMPLATE.open(encoding="utf-8-sig", newline="") as handle:
            fields = next(csv.reader(handle))
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def test_valid_authorized_listing_passes_basic_screen_but_does_not_enable_training(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = audit_csv(self.write_csv(directory, [sample_listing()]))
        self.assertTrue(report["initial_screening_passed"])
        self.assertFalse(report["training_ready"])
        self.assertEqual(report["unique_rows_passing_basic_checks"], 1)
        self.assertEqual(
            report["target_definition"],
            "asking_price_brl at listing_captured_at; advertised price only",
        )

    def test_missing_rights_or_area_definition_fails_screen(self) -> None:
        row = sample_listing()
        row["source_license_or_permission"] = ""
        row["area_type"] = "unknown"
        with tempfile.TemporaryDirectory() as directory:
            report = audit_csv(self.write_csv(directory, [row]))
        codes = report["errors"][0]["codes"]
        self.assertIn("source_permission_not_confirmed", codes)
        self.assertIn("area_definition_not_confirmed", codes)
        self.assertFalse(report["initial_screening_passed"])

    def test_duplicate_listing_ids_fail_initial_screen(self) -> None:
        first = sample_listing()
        second = sample_listing()
        second["listing_captured_at"] = "2026-08-02T12:00:00-03:00"
        with tempfile.TemporaryDirectory() as directory:
            report = audit_csv(self.write_csv(directory, [first, second]))
        self.assertFalse(report["initial_screening_passed"])
        self.assertFalse(report["training_ready"])
        self.assertEqual(report["counts"]["duplicate_listing_id_groups"], 1)

    def test_empty_template_is_not_a_training_dataset(self) -> None:
        report = audit_csv(TEMPLATE)
        self.assertEqual(report["row_count"], 0)
        self.assertFalse(report["training_ready"])


if __name__ == "__main__":
    unittest.main()
