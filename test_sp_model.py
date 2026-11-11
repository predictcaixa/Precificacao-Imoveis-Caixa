import ast
import unittest
from pathlib import Path

from train_model import (
    RAW_DATA_PATH,
    TRAINING_BLOCK_REASON,
    build_dataset_sao_paulo,
    carregar_dados,
)


class TrainingSafetyTests(unittest.TestCase):
    def test_training_source_points_to_data_folder(self):
        self.assertEqual(RAW_DATA_PATH.name, "dados_itbi_sp.csv")
        self.assertEqual(RAW_DATA_PATH.parent.name, "dados")

    def test_dataset_builder_refuses_unvalidated_fields(self):
        with self.assertRaises(RuntimeError) as error:
            build_dataset_sao_paulo()
        self.assertEqual(str(error.exception), TRAINING_BLOCK_REASON)

    def test_dataset_loader_does_not_use_legacy_derived_dataset(self):
        with self.assertRaises(RuntimeError) as error:
            carregar_dados()
        self.assertEqual(str(error.exception), TRAINING_BLOCK_REASON)

    def test_non_avm_operational_routes_fail_closed(self):
        source_path = Path(__file__).resolve().parent / "main.py"
        module = ast.parse(source_path.read_text(encoding="utf-8"))
        routes = {"stats_regioes", "gerar_relatorio"}
        functions = {
            node.name: node
            for node in module.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

        for name in routes:
            with self.subTest(route=name):
                statement = functions[name].body[0]
                self.assertIsInstance(statement, ast.Raise)
                call = statement.exc
                self.assertIsInstance(call, ast.Call)
                self.assertEqual(call.func.id, "HTTPException")
                self.assertEqual(call.args[0].value, 503)

    def test_experimental_reference_allows_unknown_iptu_pattern(self):
        source_path = Path(__file__).resolve().parent / "main.py"
        module = ast.parse(source_path.read_text(encoding="utf-8"))
        schema = next(
            node
            for node in module.body
            if isinstance(node, ast.ClassDef) and node.name == "ReferenceEstimateInput"
        )
        field = next(
            node
            for node in schema.body
            if isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "codigo_padrao_iptu"
        )
        self.assertIsInstance(field.annotation, ast.Subscript)
        self.assertEqual(field.annotation.value.id, "Optional")
        self.assertIsInstance(field.value, ast.Call)
        self.assertEqual(field.value.func.id, "Field")
        self.assertIsNone(field.value.args[0].value)


if __name__ == "__main__":
    unittest.main()
