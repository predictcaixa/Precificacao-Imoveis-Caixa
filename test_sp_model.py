from pathlib import Path

from main import ImovelInput
from train_model import build_dataset_sao_paulo


def test_imovel_input_accepts_rua_and_region_aliases():
    imovel = ImovelInput(
        regiao="zona leste",
        rua="Avenida Paulista",
        area=90,
        quartos=3,
        banheiros=2,
        vagas=1,
        idade=5,
        suite=1,
        sacada=1,
        piscina=0,
    )

    assert imovel.regiao == "america"
    assert imovel.rua == "Avenida Paulista"


def test_build_dataset_sao_paulo_extracts_expected_columns():
    csv_path = Path(__file__).resolve().parent.parent / "dados_itbi_sp.csv"
    df = build_dataset_sao_paulo(csv_path)

    required = {
        "regiao",
        "area",
        "quartos",
        "banheiros",
        "vagas",
        "idade",
        "suite",
        "sacada",
        "piscina",
        "preco",
    }

    assert required.issubset(set(df.columns))
    assert len(df) > 100
    assert len(df) < 20000
    assert df["preco"].between(50_000, 25_000_000).all()
    assert df["area"].between(30, 500).all()
    assert (df["quartos"] >= 1).all()
    assert set(df["regiao"]).issubset({"centro", "america", "anita", "norte", "sul"})
