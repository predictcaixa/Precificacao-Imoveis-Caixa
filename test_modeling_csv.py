from __future__ import annotations

import csv
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from scripts.build_modeling_csv import (
    DEFAULT_DATASET,
    DEFAULT_DICTIONARY,
    OUTPUT_FIELDS,
    build_dataset,
    write_dictionary,
)


class ModelingCsvTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = build_dataset()

    def test_dataset_preserves_audited_link_statuses(self) -> None:
        counts = Counter(row["link_status"] for row in self.rows)
        self.assertEqual(len(self.rows), 9660)
        self.assertEqual(counts, {"unique": 9658, "ambiguous": 2})
        self.assertEqual(len({row["record_id"] for row in self.rows}), len(self.rows))

    def test_evaluation_target_type_is_set_but_label_is_missing(self) -> None:
        for row in self.rows:
            self.assertEqual(row["model_training_eligible"], "false")
            self.assertEqual(row["selected_target_type"], "avaliacao")
            self.assertEqual(row["selected_target_value_brl"], "")
            self.assertEqual(
                row["target_decision_status"],
                "evaluation_target_set_by_user; evaluation_values_not_identified",
            )

    def test_total_value_matches_itbi_tax_base_for_unique_links(self) -> None:
        unique = [row for row in self.rows if row["link_status"] == "unique"]
        self.assertEqual(len(unique), 9658)
        self.assertTrue(
            all(
                row["candidate_total_origin_check"]
                == "exact_match_itbi_tax_base"
                for row in unique
            )
        )
        ambiguous = [row for row in self.rows if row["link_status"] == "ambiguous"]
        self.assertTrue(
            all(
                row["candidate_total_origin_check"]
                == "ambiguous_itbi_link_not_assessed"
                for row in ambiguous
            )
        )

    def test_unverified_attributes_are_explicitly_marked(self) -> None:
        for row in self.rows:
            self.assertEqual(row["unit_attribute_evidence_status"], "unverified")
            self.assertEqual(row["building_attribute_evidence_status"], "unverified")
        ambiguous = [row for row in self.rows if row["link_status"] == "ambiguous"]
        self.assertTrue(all(not row["itbi_declared_transaction_brl"] for row in ambiguous))
        self.assertTrue(all(not row["iptu_acc_construction_year"] for row in ambiguous))

    def test_dictionary_matches_exported_columns_and_reports_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "dictionary.csv"
            write_dictionary(path, self.rows)
            with path.open(encoding="utf-8-sig", newline="") as handle:
                dictionary = list(csv.DictReader(handle))

        self.assertEqual([row["column"] for row in dictionary], list(OUTPUT_FIELDS))
        entries = {row["column"]: row for row in dictionary}
        self.assertEqual(entries["selected_target_value_brl"]["coverage_percent"], "0.0")
        self.assertEqual(
            entries["bedrooms_raw_unverified"]["nonempty_rows"], "9660"
        )
        self.assertEqual(
            entries["bedrooms_raw_unverified"]["validation_status"],
            "not_verified",
        )


if __name__ == "__main__":
    unittest.main()
