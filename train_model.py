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
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sklearn.linear_model import LinearRegression, Ridge
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.model_selection import train_test_split, cross_val_score, KFold
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline

warnings.filterwarnings("ignore")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(BASE_DIR, "data", "imoveis_joinville.csv")
MODELS_DIR = os.path.join(BASE_DIR, "models")
os.makedirs(MODELS_DIR, exist_ok=True)


# ─── 1. CARREGAR E PREPARAR DADOS ──────────────────────────────────────────────

def carregar_dados():
    df = pd.read_csv(DATA_PATH)
    print(f"[INFO] Dataset carregado: {len(df)} registros, {df.shape[1]} colunas")
    print(f"[INFO] Regiões: {df['regiao'].unique().tolist()}")
    print(f"[INFO] Preço médio: R$ {df['preco'].mean():,.0f}")
    return df


def preparar_features(df):
    """
    Engenharia de features:
    - Dummy encoding para região
    - Feature de interação: área × quartos
    - Log do preço como target (melhora distribuição)
    """
    # Features numéricas
    num_cols = ["area", "quartos", "banheiros", "vagas", "idade", "suite", "sacada", "piscina"]

    # Dummies para região (drop_first para evitar multicolinearidade)
    dummies = pd.get_dummies(df["regiao"], prefix="regiao", drop_first=False)

    # Feature de interação
    df = df.copy()
    df["area_por_quarto"] = df["area"] / df["quartos"].replace(0, 1)
    df["luxo_score"] = df["suite"] + df["sacada"] + df["piscina"] * 2

    extra_cols = ["area_por_quarto", "luxo_score"]

    X = pd.concat([df[num_cols + extra_cols].reset_index(drop=True),
                   dummies.reset_index(drop=True)], axis=1)
    y = df["preco"].values

    print(f"[INFO] Features: {list(X.columns)}")
    return X, y, list(X.columns)


# ─── 2. TREINAR MODELOS ─────────────────────────────────────────────────────────

def treinar_e_avaliar(X, y, feature_names):
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    modelos = {
        "linear": Pipeline([
            ("scaler", StandardScaler()),
            ("model", Ridge(alpha=10.0))
        ]),
        "random_forest": RandomForestRegressor(
            n_estimators=300,
            max_depth=8,
            min_samples_split=4,
            min_samples_leaf=2,
            random_state=42
        ),
        "gradient_boosting": GradientBoostingRegressor(
            n_estimators=200,
            learning_rate=0.08,
            max_depth=4,
            subsample=0.8,
            random_state=42
        ),
    }

    resultados = {}
    kf = KFold(n_splits=5, shuffle=True, random_state=42)

    print("\n" + "="*60)
    print("AVALIAÇÃO DOS MODELOS")
    print("="*60)

    melhor_modelo = None
    melhor_r2 = -99

    for nome, modelo in modelos.items():
        modelo.fit(X_train, y_train)
        y_pred = modelo.predict(X_test)

        mae  = mean_absolute_error(y_test, y_pred)
        rmse = np.sqrt(mean_squared_error(y_test, y_pred))
        r2   = r2_score(y_test, y_pred)
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

    # Importância de features (só modelos baseados em árvore)
    importancias = {}
    for nome, modelo in modelos.items():
        m = modelo.named_steps["model"] if hasattr(modelo, "named_steps") else modelo
        if hasattr(m, "feature_importances_"):
            imp = dict(zip(feature_names, m.feature_importances_.tolist()))
            importancias[nome] = dict(sorted(imp.items(), key=lambda x: -x[1]))

    return modelos, resultados, importancias, melhor_modelo, X_test, y_test


# ─── 3. GERAR GRÁFICOS ──────────────────────────────────────────────────────────

def gerar_graficos(modelos, X_test, y_test, importancias):
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    fig.suptitle("Avaliação dos Modelos — Precificação de Imóveis Joinville", fontsize=13)

    cores = ["#185FA5", "#1D9E75", "#BA7517"]
    nomes_display = ["Regressão Ridge", "Random Forest", "Gradient Boosting"]

    for i, (nome_modelo, cor, display) in enumerate(zip(
        ["linear", "random_forest", "gradient_boosting"], cores, nomes_display
    )):
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
        ax.text(0.05, 0.92, f"R² = {r2:.3f}", transform=ax.transAxes,
                fontsize=10, color=cor, fontweight="bold")
        ax.grid(True, alpha=0.2)

    plt.tight_layout()
    path_scatter = os.path.join(MODELS_DIR, "scatter_predicoes.png")
    plt.savefig(path_scatter, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[INFO] Gráfico salvo: {path_scatter}")

    # Importância de features — Random Forest
    if "random_forest" in importancias:
        imp = importancias["random_forest"]
        top_n = dict(list(imp.items())[:10])
        fig2, ax2 = plt.subplots(figsize=(9, 5))
        bars = ax2.barh(list(top_n.keys())[::-1], list(top_n.values())[::-1], color="#1D9E75", alpha=0.85)
        ax2.set_xlabel("Importância relativa", fontsize=10)
        ax2.set_title("Top 10 — Importância de Features (Random Forest)", fontsize=11)
        ax2.grid(True, axis="x", alpha=0.2)
        for bar, val in zip(bars, list(top_n.values())[::-1]):
            ax2.text(bar.get_width() + 0.002, bar.get_y() + bar.get_height()/2,
                     f"{val:.3f}", va="center", fontsize=9)
        plt.tight_layout()
        path_imp = os.path.join(MODELS_DIR, "importancia_features.png")
        plt.savefig(path_imp, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"[INFO] Gráfico salvo: {path_imp}")


# ─── 4. SALVAR ARTEFATOS ────────────────────────────────────────────────────────

def salvar_artefatos(modelos, resultados, importancias, feature_names):
    # Serializar cada modelo
    for nome, modelo in modelos.items():
        path = os.path.join(MODELS_DIR, f"modelo_{nome}.pkl")
        with open(path, "wb") as f:
            pickle.dump(modelo, f)
        print(f"[INFO] Modelo salvo: {path}")

    # Metadados JSON
    meta = {
        "feature_names": feature_names,
        "regioes": ["centro", "america", "anita", "norte", "sul"],
        "metricas": resultados,
        "importancias": importancias,
        "modelo_principal": "random_forest",
    }
    path_meta = os.path.join(MODELS_DIR, "metadata.json")
    with open(path_meta, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"[INFO] Metadados salvos: {path_meta}")


# ─── 5. MAIN ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("SISTEMA DE PRECIFICAÇÃO DE IMÓVEIS — TREINAMENTO")
    print("=" * 60)

    df = carregar_dados()
    X, y, feature_names = preparar_features(df)
    modelos, resultados, importancias, melhor, X_test, y_test = treinar_e_avaliar(X, y, feature_names)
    gerar_graficos(modelos, X_test, y_test, importancias)
    salvar_artefatos(modelos, resultados, importancias, feature_names)

    print("\n" + "="*60)
    print("TREINAMENTO CONCLUÍDO COM SUCESSO!")
    print(f"Modelos salvos em: {MODELS_DIR}/")
    print("="*60)


if __name__ == "__main__":
    main()
