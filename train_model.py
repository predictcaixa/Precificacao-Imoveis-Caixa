"""Training is intentionally blocked until data provenance and validation are approved."""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
RAW_DATA_PATH = BASE_DIR / "dados" / "dados_itbi_sp.csv"
DATASET_PATH = BASE_DIR / "dados" / "dados_sp_ref.csv"
MODELS_DIR = BASE_DIR / "models"

TRAINING_BLOCK_REASON = (
    "Treinamento bloqueado: o dataset legado contém atributos inferidos sem evidência "
    "e a semântica/associação da base enriquecida ainda não foi aprovada. Consulte "
    "docs/diagnostico_tecnico_base.md antes de definir o dataset de treino."
)


def build_dataset_sao_paulo(raw_path: str | Path | None = None):
    raise RuntimeError(TRAINING_BLOCK_REASON)


def carregar_dados():
    raise RuntimeError(TRAINING_BLOCK_REASON)


def main():
    raise RuntimeError(TRAINING_BLOCK_REASON)


if __name__ == "__main__":
    main()
