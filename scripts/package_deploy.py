"""Build the API-only package for a Python host connected to Supabase Postgres."""

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
)


def copy_file(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"Arquivo necessÃ¡rio ao deploy nÃ£o encontrado: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def package(output: Path) -> None:
    output = output.resolve()
    if output.exists():
        raise FileExistsError(
            f"Destino jÃ¡ existe: {output}. Escolha uma pasta nova para o pacote."
        )
    output.mkdir(parents=True)
    copy_file(ROOT / "main.py", output / "main.py")
    copy_file(ROOT / "requirements-api.txt", output / "requirements.txt")
    for module in API_MODULES:
        copy_file(ROOT / "scripts" / module, output / "scripts" / module)

    shutil.copytree(ROOT / "models" / "offer_avm", output / "models" / "offer_avm")
    copy_file(ROOT / "models" / "itbi_reference_2026.json", output / "models" / "itbi_reference_2026.json")
    copy_file(ROOT / "dados" / "derivados" / "catalogo_bases.json", output / "dados" / "derivados" / "catalogo_bases.json")
    copy_file(ROOT / "dados" / "derivados" / "avaliacoes_imoveis_template.csv", output / "dados" / "derivados" / "avaliacoes_imoveis_template.csv")
    copy_file(
        ROOT / "scripts" / "dados" / "caixa_sp_validacao_audit.json",
        output / "scripts" / "dados" / "caixa_sp_validacao_audit.json",
    )
    copy_file(ROOT / "docs" / "deploy.md", output / "DEPLOY.md")
    (output / "Procfile").write_text(
        "web: uvicorn main:app --host 0.0.0.0 --port $PORT\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "deploy" / "api")
    args = parser.parse_args()
    package(args.output)
    print(f"Pacote somente API criado em: {args.output.resolve()}")


if __name__ == "__main__":
    main()
