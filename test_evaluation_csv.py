from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from scripts.audit_evaluation_csv import (
    DEFAULT_INPUT,
    REQUIRED_COLUMNS,
    audit_csv,
)


def valid_appraisal() -> dict[str, str]:
    row = {field: "" for field in REQUIRED_COLUMNS}
    row.update(
        {
            "valuation_record_id": "appraisal-001",
            "property_token": "sha256:" + "b" * 64,
            "valuation_value_brl": "650000",
            "valuation_date": "2026-08-01",
            "valuation_purpose": "market_value",
            "value_basis": "market_value",
            "valuation_method": "comparative_market_approach",
            "appraisal_status": "final",
            "property_type": "apartment",
            "city": "São Paulo",
            "state": "SP",
            "unit_match_status": "confirmed",
            "area_value_m2": "75",
            "area_type": "private",
            "area_source": "official_unit_document",
            "area_evidence_ref": "doc-001#area",
            "target_document_ref": "doc-001",
            "target_document_sha256": "a" * 64,
            "source_permission": "authorized",
            "review_status": "approved",
        }
    )
    return row


class EvaluationCsvAuditTests(unittest.TestCase):
    def write_csv(self, directory: str, rows: list[dict[str, str]]) -> Path:
        path = Path(directory) / "appraisals.csv"
        fields = sorted(REQUIRED_COLUMNS) + [
            "bedrooms",
            "bedrooms_evidence_ref",
            "bedrooms_value_type",
            "bedrooms_entity_scope",
        ]
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def test_template_is_empty_and_does_not_enable_training(self) -> None:
        report = audit_csv(DEFAULT_INPUT)
        self.assertEqual(report["row_count"], 0)
        self.assertFalse(report["training_ready"])
        self.assertEqual(report["candidate_rows_for_expert_review"], 0)

    def test_valid_market_appraisal_is_candidate_only_not_training_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = audit_csv(self.write_csv(directory, [valid_appraisal()]))
        self.assertEqual(report["candidate_rows_for_expert_review"], 1)
        self.assertFalse(report["training_ready"])
        self.assertEqual(report["target_definition"], "final reviewed market-value appraisal in BRL at valuation_date")

    def test_itbi_fiscal_value_or_offer_cannot_be_passed_as_appraisal_basis(self) -> None:
        row = valid_appraisal()
        row["value_basis"] = "itbi_declared_transaction"
        with tempfile.TemporaryDirectory() as directory:
            report = audit_csv(self.write_csv(directory, [row]))
        error_codes = report["errors"][0]["codes"]
        self.assertIn("valuation_basis_not_market_value", error_codes)
        self.assertEqual(report["candidate_rows_for_expert_review"], 0)

    def test_personal_identifier_and_unconfirmed_unit_block_row(self) -> None:
        row = valid_appraisal()
        row["property_token"] = "owner@example.com"
        row["unit_match_status"] = "unconfirmed"
        with tempfile.TemporaryDirectory() as directory:
            report = audit_csv(self.write_csv(directory, [row]))
        error_codes = report["errors"][0]["codes"]
        self.assertNotIn("valuation_record_id", report["errors"][0])
        self.assertIn("property_token_must_be_sha256_pseudonym", error_codes)
        self.assertIn("appraised_unit_identity_not_confirmed", error_codes)

    def test_unit_level_feature_requires_evidence_and_warns_on_wrong_scope(self) -> None:
        row = valid_appraisal()
        row.update(
            {
                "bedrooms": "2",
                "bedrooms_evidence_ref": "doc-001#floorplan",
                "bedrooms_value_type": "extracted",
                "bedrooms_entity_scope": "building",
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            report = audit_csv(self.write_csv(directory, [row]))
        codes = {warning["code"] for warning in report["warnings"]}
        self.assertIn("feature_entity_scope_mismatch", codes)
        self.assertEqual(
            report["feature_evidence_coverage"]["bedrooms"]["rows_with_evidence"],
            1,
        )


if __name__ == "__main__":
    unittest.main()
