"""Build the reduced FastAPI and web UI package for Vercel."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_MODULES = (
    "audit_caixa_validation.py",
    "audit_data_sources.py",
    "audit_evaluation_csv.py",
    "audit_offer_csv.py",
    "build_data_catalog.py",
    "build_peer_comparison_workbook.py",
    "experimental_reference.py",
    "offer_avm_store.py",
    "process_comparison_workbook.py",
    "serve_offer_avm.py",
    "train_offer_avm.py",
    "validate_caixa_calculations.py",
)
OBSOLETE_PACKAGE_FILES = (
    "Procfile",
    "models/offer_avm/feature_importance.csv",
    "models/offer_avm/offer_avm_catboost.cbm",
    "models/offer_avm/offer_avm_xgboost.joblib",
    "models/offer_avm/test_residuals.csv",
)
OBSOLETE_PACKAGE_DIRECTORIES = ("__pycache__", "scripts/__pycache__")
VERCEL_REQUIREMENTS = """\
fastapi>=0.115,<1
psycopg[binary]>=3.2,<4
openpyxl>=3.1.5
pandas>=3.1,<4
scikit-learn==1.9.1
"""


def copy_file(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"Arquivo necessÃ¡rio ao deploy nÃ£o encontrado: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def package(output: Path, replace: bool = False) -> None:
    output = output.resolve()
    if output.exists() and not replace:
        raise FileExistsError(
            f"Destino jÃ¡ existe: {output}. Escolha uma pasta nova para o pacote."
        )
    output.mkdir(parents=True, exist_ok=True)
    if replace:
        for relative_path in OBSOLETE_PACKAGE_FILES:
            obsolete_path = output / relative_path
            if obsolete_path.is_file():
                obsolete_path.unlink()
        for relative_path in OBSOLETE_PACKAGE_DIRECTORIES:
            obsolete_directory = output / relative_path
            if obsolete_directory.is_dir():
                shutil.rmtree(obsolete_directory)
    copy_file(ROOT / "main.py", output / "main.py")
    copy_file(ROOT / "index.html", output / "index.html")
    (output / "requirements.txt").write_text(VERCEL_REQUIREMENTS, encoding="utf-8")
    (output / ".python-version").write_text("3.13\n", encoding="utf-8")
    for module in API_MODULES:
        copy_file(ROOT / "scripts" / module, output / "scripts" / module)

    copy_file(
        ROOT / "models" / "offer_avm" / "avm_report.json",
        output / "models" / "offer_avm" / "avm_report.json",
    )
    copy_file(
        ROOT / "models" / "offer_avm" / "offer_avm.joblib",
        output / "models" / "offer_avm" / "offer_avm.joblib",
    )
    copy_file(ROOT / "models" / "itbi_reference_2026.json", output / "models" / "itbi_reference_2026.json")
    copy_file(ROOT / "dados" / "derivados" / "catalogo_bases.json", output / "dados" / "derivados" / "catalogo_bases.json")
    copy_file(ROOT / "dados" / "derivados" / "avaliacoes_imoveis_template.csv", output / "dados" / "derivados" / "avaliacoes_imoveis_template.csv")
    copy_file(
        ROOT / "scripts" / "dados" / "caixa_sp_validacao_audit.json",
        output / "scripts" / "dados" / "caixa_sp_validacao_audit.json",
    )
    copy_file(ROOT / "docs" / "deploy.md", output / "DEPLOY.md")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "deploy" / "api")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Atualiza arquivos do pacote existente e remove artefatos obsoletos conhecidos.",
    )
    args = parser.parse_args()
    package(args.output, replace=args.replace)
    print(f"Pacote somente API criado em: {args.output.resolve()}")


if __name__ == "__main__":
    main()
