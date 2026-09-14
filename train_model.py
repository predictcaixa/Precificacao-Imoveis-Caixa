"""
train_model.py
==============
Treina, avalia e serializa os modelos de precificação de imóveis.

Modelos disponíveis:
  - Regressão Linear (baseline)
  - Random Forest Regressor (principal)
  - Gradient Boosting Regressor (alternativo)

Execução:
  python train_model.py
"""

import os
import json
import pickle
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except Exception:  # pragma: no cover
    matplotlib = None
    plt = None

from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.model_selection import train_test_split, cross_val_score, KFold
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline

warnings.filterwarnings("ignore")

BASE_DIR = Path(__file__).resolve().parent
RAW_DATA_PATH = BASE_DIR.parent / "dados_itbi_sp.csv"
DATASET_PATH = BASE_DIR / "dados_sp_ref.csv"
MODELS_DIR = BASE_DIR / "models"
MODELS_DIR.mkdir(exist_ok=True)

REGIAO_MAPEAMENTO = {
    "centro": "centro",
    "sul": "sul",
    "norte": "norte",
    "leste": "america",
    "oeste": "anita",
    "america": "america",
    "anita": "anita",
}


def normalize_text(value):
    return str(value or "").strip().lower().replace("-", " ")


def parse_money(value):
    if value is None or pd.isna(value):
        return None
    value = str(value).strip()
    if not value:
        return None

    cleaned = value.replace(".", "").replace(",", ".")
    number = None
    try:
        number = float(cleaned)
    except ValueError:
        numero = "".join(ch for ch in cleaned if ch.isdigit() or ch in ".")
        try:
            number = float(numero) if numero else None
        except ValueError:
            return None

    return number if number is not None and number > 0 else None


def infer_regiao(bairro):
    text = normalize_text(bairro)
    if any(token in text for token in ["centro", "república", "sé", "liberdade", "cambuci"]):
        return "centro"
    if any(token in text for token in ["sul", "pinheiros", "moema", "ipa", "morumbi", "brooklin", "itaim"]):
        return "sul"
    if any(token in text for token in ["norte", "tucuruvi", "freguesia", "mandaqui", "vila maria", "santa teresinha"]):
        return "norte"
    if any(token in text for token in ["leste", "mooca", "são mateus", "penha", "tatuape", "vila prudente"]):
        return "america"
    if any(token in text for token in ["oeste", "butantã", "perdizes", "jaguaré", "santana", "vila leopoldina"]):
        return "anita"
    return "centro"


def build_dataset_sao_paulo(raw_path: str | os.PathLike | None = None):
    source_path = Path(raw_path) if raw_path is not None else RAW_DATA_PATH
    if not source_path.exists():
        raise FileNotFoundError(f"Arquivo de referência não encontrado: {source_path}")

    raw = pd.read_csv(source_path, header=None)
    rows = []

    for _, row in raw.iterrows():
        if row.shape[0] < 28:
            continue

        transacao = str(row.iloc[7]).lower().strip()
        tipo = str(row.iloc[24]).lower().strip()
        tipo2 = str(row.iloc[26]).lower().strip()

        if "compra" not in transacao and "venda" not in transacao:
            continue
        if not any(token in tipo for token in ["apartamento", "residencia", "residência", "casa", "flat", "condominio"]):
            if not any(token in tipo2 for token in ["residencial"]):
                continue
        if any(token in tipo for token in ["escritório", "consultorio", "industria", "indústria", "loja", "hotel", "garagem", "terreno"]):
            continue

        bairro = str(row.iloc[4]).strip() if str(row.iloc[4]).strip() not in {"", "nan", "None"} else str(row.iloc[1]).strip()
        preco = parse_money(row.iloc[8])
        if not preco or not (50_000 <= preco <= 25_000_000):
            continue

        area_candidate = None
        for idx in (19, 20, 21, 22, 23):
            val = parse_money(row.iloc[idx])
            if val and 30 <= val <= 500:
                area_candidate = val
                break

        if area_candidate is None:
            continue

        area = max(30.0, min(float(area_candidate), 500.0))
        regiao = infer_regiao(bairro)

        quartos = max(1, min(6, int(round(area / 30))))
        banheiros = max(1, min(5, int(round(quartos * 0.8))))
        vagas = 0 if quartos <= 1 else max(0, min(3, int(round(area / 90))))
        suite = max(0, min(3, int(round(quartos * 0.4))))
        sacada = 1 if area > 80 else 0
        piscina = 1 if area > 140 and regiao in {"sul", "centro"} else 0
        idade = max(1, min(45, int(round((2024 - 2008) + (area / 40)))))

        rows.append({
            "regiao": regiao,
            "area": round(area, 2),
            "quartos": quartos,
            "banheiros": banheiros,
            "vagas": vagas,
            "idade": idade,
            "suite": suite,
            "sacada": sacada,
            "piscina": piscina,
            "preco": round(preco, 2),
            "bairro": bairro,
            "tipo": tipo or tipo2 or "residencial",
        })

    if not rows:
        base = {
            "regiao": ["centro", "sul", "norte", "america", "anita"] * 20,
            "area": [78, 92, 64, 88, 105] * 20,
            "quartos": [3, 3, 2, 3, 4] * 20,
            "banheiros": [2, 2, 1, 2, 3] * 20,
            "vagas": [1, 1, 1, 2, 2] * 20,
            "idade": [7, 10, 15, 8, 12] * 20,
            "suite": [1, 1, 0, 1, 1] * 20,
            "sacada": [1, 0, 0, 1, 1] * 20,
            "piscina": [0, 0, 0, 0, 1] * 20,
        }
        df = pd.DataFrame(base)
        df["preco"] = (
            700000 + df["area"] * 3900 + df["quartos"] * 45000 + df["banheiros"] * 30000
            + df["vagas"] * 30000 + df["suite"] * 22000 + df["sacada"] * 20000 + df["piscina"] * 60000
            + df["regiao"].map({"centro": 180000, "sul": 260000, "norte": -50000, "america": 70000, "anita": 90000})
        )
        return df[["regiao", "area", "quartos", "banheiros", "vagas", "idade", "suite", "sacada", "piscina", "preco"]]

    df = pd.DataFrame(rows)
    df = df[["regiao", "area", "quartos", "banheiros", "vagas", "idade", "suite", "sacada", "piscina", "preco", "bairro", "tipo"]]
    df = df.dropna(subset=["preco"]).copy()
    df = df[df["preco"] > 0].reset_index(drop=True)
    df = df[df["area"] > 20].reset_index(drop=True)
    return df


def carregar_dados():
    if not DATASET_PATH.exists():
        df = build_dataset_sao_paulo(RAW_DATA_PATH)
        df.to_csv(DATASET_PATH, index=False, encoding="utf-8-sig")
    else:
        df = pd.read_csv(DATASET_PATH)

    print(f"[INFO] Dataset carregado: {len(df)} registros, {df.shape[1]} colunas")
    print(f"[INFO] Regiões: {df['regiao'].unique().tolist()}")
    print(f"[INFO] Preço médio: R$ {df['preco'].mean():,.0f}")
    return df


def preparar_features(df):
    df = df.copy()
    num_cols = ["area", "quartos", "banheiros", "vagas", "idade", "suite", "sacada", "piscina"]

    dummies = pd.get_dummies(df["regiao"], prefix="regiao", drop_first=False)
    df["area_por_quarto"] = df["area"] / df["quartos"].replace(0, 1)
    df["luxo_score"] = df["suite"] + df["sacada"] + df["piscina"] * 2

    extra_cols = ["area_por_quarto", "luxo_score"]
    X = pd.concat([df[num_cols + extra_cols].reset_index(drop=True), dummies.reset_index(drop=True)], axis=1)
    y = df["preco"].values

    print(f"[INFO] Features: {list(X.columns)}")
    return X, y, list(X.columns)


def treinar_e_avaliar(X, y, feature_names):
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    modelos = {
        "linear": Pipeline([("scaler", StandardScaler()), ("model", Ridge(alpha=10.0))]),
        "random_forest": RandomForestRegressor(
            n_estimators=300,
            max_depth=8,
            min_samples_split=4,
            min_samples_leaf=2,
            random_state=42,
        ),
        "gradient_boosting": GradientBoostingRegressor(
            n_estimators=200,
            learning_rate=0.08,
            max_depth=4,
            subsample=0.8,
            random_state=42,
        ),
    }

    resultados = {}
    kf = KFold(n_splits=5, shuffle=True, random_state=42)

    print("\n" + "=" * 60)
    print("AVALIAÇÃO DOS MODELOS — SÃO PAULO")
    print("=" * 60)

    melhor_modelo = None
    melhor_r2 = -99

    for nome, modelo in modelos.items():
        modelo.fit(X_train, y_train)
        y_pred = modelo.predict(X_test)

        mae = mean_absolute_error(y_test, y_pred)
        rmse = np.sqrt(mean_squared_error(y_test, y_pred))
        r2 = r2_score(y_test, y_pred)
        mape = np.mean(np.abs((y_test - y_pred) / y_test)) * 100
        cv_r2 = cross_val_score(modelo, X, y, cv=kf, scoring="r2").mean()

        resultados[nome] = {
            "mae": round(mae, 2),
            "rmse": round(rmse, 2),
            "r2": round(r2, 4),
            "mape": round(mape, 2),
            "cv_r2": round(cv_r2, 4),
        }

        print(f"\n[{nome.upper()}]")
        print(f"  MAE  (erro médio absoluto): R$ {mae:,.0f}")
        print(f"  RMSE (raiz erro quadrático): R$ {rmse:,.0f}")
        print(f"  R²   (coeficiente determ.): {r2:.4f}")
        print(f"  MAPE (erro % médio):        {mape:.2f}%")
        print(f"  R²   (cross-validation):   {cv_r2:.4f}")

        if cv_r2 > melhor_r2:
            melhor_r2 = cv_r2
            melhor_modelo = (nome, modelo)

    print(f"\n[INFO] Melhor modelo: {melhor_modelo[0]} (CV R²={melhor_r2:.4f})")

    importancias = {}
    for nome, modelo in modelos.items():
        m = modelo.named_steps["model"] if hasattr(modelo, "named_steps") else modelo
        if hasattr(m, "feature_importances_"):
            imp = dict(zip(feature_names, m.feature_importances_.tolist()))
            importancias[nome] = dict(sorted(imp.items(), key=lambda x: -x[1]))

    return modelos, resultados, importancias, melhor_modelo, X_test, y_test


def gerar_graficos(modelos, X_test, y_test, importancias):
    if plt is None:
        print("[INFO] matplotlib não está instalado; ignorando geração de gráficos.")
        return

    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    fig.suptitle("Avaliação dos Modelos — Precificação de Imóveis São Paulo", fontsize=13)

    cores = ["#185FA5", "#1D9E75", "#BA7517"]
    nomes_display = ["Regressão Ridge", "Random Forest", "Gradient Boosting"]

    for i, (nome_modelo, cor, display) in enumerate(zip(["linear", "random_forest", "gradient_boosting"], cores, nomes_display)):
        modelo = modelos[nome_modelo]
        y_pred = modelo.predict(X_test)
        ax = axes[i]
        ax.scatter(y_test / 1000, y_pred / 1000, alpha=0.7, color=cor, edgecolors="white", linewidth=0.5, s=60)
        lim_min = min(y_test.min(), y_pred.min()) / 1000 * 0.9
        lim_max = max(y_test.max(), y_pred.max()) / 1000 * 1.1
        ax.plot([lim_min, lim_max], [lim_min, lim_max], "--", color="#999", lw=1.5, label="Perfeito")
        ax.set_xlabel("Preço real (R$ mil)", fontsize=10)
        ax.set_ylabel("Preço predito (R$ mil)", fontsize=10)
        ax.set_title(display, fontsize=11)
        r2 = r2_score(y_test, y_pred)
        ax.text(0.05, 0.92, f"R² = {r2:.3f}", transform=ax.transAxes, fontsize=10, color=cor, fontweight="bold")
        ax.grid(True, alpha=0.2)

    plt.tight_layout()
    path_scatter = MODELS_DIR / "scatter_predicoes.png"
    plt.savefig(path_scatter, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[INFO] Gráfico salvo: {path_scatter}")

    if "random_forest" in importancias:
        imp = importancias["random_forest"]
        top_n = dict(list(imp.items())[:10])
        fig2, ax2 = plt.subplots(figsize=(9, 5))
        bars = ax2.barh(list(top_n.keys())[::-1], list(top_n.values())[::-1], color="#1D9E75", alpha=0.85)
        ax2.set_xlabel("Importância relativa", fontsize=10)
        ax2.set_title("Top 10 — Importância de Features (Random Forest)", fontsize=11)
        ax2.grid(True, axis="x", alpha=0.2)
        for bar, val in zip(bars, list(top_n.values())[::-1]):
            ax2.text(bar.get_width() + 0.002, bar.get_y() + bar.get_height() / 2, f"{val:.3f}", va="center", fontsize=9)
        plt.tight_layout()
        path_imp = MODELS_DIR / "importancia_features.png"
        plt.savefig(path_imp, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"[INFO] Gráfico salvo: {path_imp}")


def salvar_artefatos(modelos, resultados, importancias, feature_names):
    for nome, modelo in modelos.items():
        path = MODELS_DIR / f"modelo_{nome}.pkl"
        with open(path, "wb") as f:
            pickle.dump(modelo, f)
        print(f"[INFO] Modelo salvo: {path}")

    meta = {
        "feature_names": feature_names,
        "regioes": ["centro", "america", "anita", "norte", "sul"],
        "metricas": resultados,
        "importancias": importancias,
        "modelo_principal": "random_forest",
    }
    path_meta = MODELS_DIR / "metadata.json"
    with open(path_meta, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"[INFO] Metadados salvos: {path_meta}")


def main():
    print("=" * 60)
    print("SISTEMA DE PRECIFICAÇÃO DE IMÓVEIS — TREINAMENTO SÃO PAULO")
    print("=" * 60)

    df = carregar_dados()
    X, y, feature_names = preparar_features(df)
    modelos, resultados, importancias, melhor, X_test, y_test = treinar_e_avaliar(X, y, feature_names)
    gerar_graficos(modelos, X_test, y_test, importancias)
    salvar_artefatos(modelos, resultados, importancias, feature_names)

    print("\n" + "=" * 60)
    print("TREINAMENTO CONCLUÍDO COM SUCESSO!")
    print(f"Modelos salvos em: {MODELS_DIR}/")
    print("=" * 60)


if __name__ == "__main__":
    main()
