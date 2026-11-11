"""
geocode_geosampa_join.py
Limpa a amostra da Caixa, geocodifica os endereços (Nominatim/OSM) e cruza cada
ponto com a camada de LOTES do GeoSampa para obter setor-quadra-lote (SQL).

Uso (a partir da pasta scripts):
  python extrair_dados.py \
      --input dados/caixa_sp_validacao.csv \
      --output dados/caixa_sp_validacao_processada.csv \
      --max-geocode 0

Para cruzar com a camada de lotes do GeoSampa, baixe-a e armazene-a localmente:
  python extrair_dados.py \
      --input dados/caixa_sp_validacao.csv \
      --lotes dados/geosampa/lote.shp \
      --output dados/caixa_sp_validacao_sql.csv

Dependências:
  pip install pandas requests geopandas pyogrio shapely

Se a camada de lotes tiver nomes de colunas diferentes, o script lista as colunas e
você informa --setor-col, --quadra-col e --lote-col.

Sem --lotes, só limpa e geocodifica (útil para conferir os pontos antes).
Se o CSV já tiver colunas lat/lon, o geocoding é pulado nessas linhas.
Use --max-geocode 0 para não enviar endereços a um serviço externo.

IMPORTANTE:
 - Geocodificação por endereço é aproximada; confira o campo geocode_precisao.
 - O SQL aqui é do LOTE (10 dígitos: setor 3 + quadra 3 + lote 4). O SQL do ITBI de
   apartamentos pode ter dígitos extras de condomínio; compare pelos 10 primeiros.
 - O valor de avaliação da Caixa é de imóveis retomados; não é valor de mercado final.
"""
from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
from pathlib import Path

import pandas as pd
import requests

HEADERS = {"User-Agent": "pesquisa-avm-validacao/1.0 (uso academico)"}
NOMINATIM = "https://nominatim.openstreetmap.org/search"
CRS_GEOSAMPA = "EPSG:31983"  # SIRGAS 2000 / UTM 23S, padrão do GeoSampa


# ───────────────────────── 1. Limpeza ─────────────────────────
def strip_accents(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in text if not unicodedata.combining(c)).lower().strip()


def clean(df: pd.DataFrame, area_max: float, m2_min: float, m2_max: float) -> pd.DataFrame:
    df = df.copy()
    for col in df.select_dtypes(include=["object", "string"]).columns:
        df[col] = df[col].astype("string").str.strip()
    df = df.drop_duplicates(subset=["n_do_imovel"])

    # logradouro + número do prédio, a partir de "RUA X, N. 215, Apto 121, ..."
    m = df["endereco"].str.extract(r"^(?P<rua>.*?),\s*N\.?\s*(?P<num>\d+)", flags=re.IGNORECASE)
    df["logradouro"] = m["rua"].str.strip()
    df["numero"] = m["num"]
    df["predio_id"] = (
        df["logradouro"].fillna("").map(strip_accents) + "|" + df["numero"].fillna("")
        + "|" + df["bairro"].fillna("").map(strip_accents)
    )
    df.loc[df["numero"].isna(), "predio_id"] = "sem_numero|" + df["n_do_imovel"].astype(str)

    # Sinalizadores (não apaga nada; o filtro é feito no final)
    flags = pd.Series("", index=df.index)
    flags[df["area_ref_m2"] > area_max] += "area_acima_limite;"
    flags[df["avaliacao_brl_m2"] < m2_min] += "m2_abaixo_limite;"
    flags[df["avaliacao_brl_m2"] > m2_max] += "m2_acima_limite;"
    flags[df["numero"].isna()] += "endereco_sem_numero;"
    df["flag_qualidade"] = flags
    df["n_unidades_no_predio"] = df.groupby("predio_id")["n_do_imovel"].transform("count")
    return df


# ───────────────────────── 2. Geocodificação ─────────────────────────
def _nominatim(query: str) -> dict | None:
    resp = requests.get(
        NOMINATIM,
        params={"q": query, "format": "jsonv2", "limit": 1, "countrycodes": "br"},
        headers=HEADERS, timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data:
        return None
    hit = data[0]
    kind = hit.get("addresstype") or hit.get("type") or ""
    precision = "numero" if kind in ("house", "building", "apartments", "residential") else "via"
    return {"lat": float(hit["lat"]), "lon": float(hit["lon"]), "precisao": precision}


def geocode_buildings(df: pd.DataFrame, cache_path: Path, max_calls: int) -> pd.DataFrame:
    """Geocodifica uma vez por PRÉDIO (não por apartamento) e usa cache em disco."""
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    work = df.drop_duplicates("predio_id")[["predio_id", "logradouro", "numero", "bairro"]]
    calls = 0
    for _, r in work.iterrows():
        key = r["predio_id"]
        if key in cache or pd.isna(r["logradouro"]):
            continue
        if calls >= max_calls:
            break
        queries = [
            f"{r['logradouro']}, {r['numero']}, {r['bairro']}, São Paulo, SP, Brasil",
            f"{r['logradouro']}, {r['numero']}, São Paulo, SP, Brasil",
        ]
        result = None
        for q in queries:
            try:
                result = _nominatim(q)
            except Exception as exc:  # rede/limite: não aborta o lote
                print(f"  aviso: falha em '{q}': {exc}")
            calls += 1
            time.sleep(1.1)  # política de uso do Nominatim: ~1 req/s
            if result:
                break
        cache[key] = result
        if calls % 25 == 0:
            cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            print(f"  geocodificados (chamadas): {calls}")
    cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    df = df.copy()
    for col in ("lat", "lon", "geocode_precisao"):
        if col not in df.columns:
            df[col] = pd.NA
    hits = df["predio_id"].map(cache)
    for i, hit in hits.items():
        if isinstance(hit, dict) and pd.isna(df.at[i, "lat"]):
            df.at[i, "lat"], df.at[i, "lon"] = hit["lat"], hit["lon"]
            df.at[i, "geocode_precisao"] = hit["precisao"]
    return df


# ───────────────────────── 3. Cruzamento com GeoSampa ─────────────────────────
def pick_col(columns, explicit: str | None, *keywords: str) -> str | None:
    if explicit:
        return explicit
    for col in columns:
        low = col.lower()
        if all(k in low for k in keywords):
            return col
    return None


def join_lotes(df: pd.DataFrame, lotes_path: Path, setor_col, quadra_col, lote_col,
               max_dist_m: float) -> pd.DataFrame:
    import geopandas as gpd

    # lê só 1 linha para descobrir CRS e colunas
    probe = gpd.read_file(lotes_path, rows=1)
    layer_crs = probe.crs or CRS_GEOSAMPA
    cols = [c for c in probe.columns if c != "geometry"]

    setor_col = pick_col(cols, setor_col, "setor")
    quadra_col = pick_col(cols, quadra_col, "quadra")
    lote_col = pick_col(cols, lote_col, "lote")
    if not (setor_col and quadra_col and lote_col):
        raise SystemExit(
            "Não identifiquei as colunas de setor/quadra/lote.\n"
            f"Colunas da camada: {cols}\n"
            "Informe --setor-col, --quadra-col e --lote-col."
        )
    print(f"Colunas usadas: setor={setor_col} quadra={quadra_col} lote={lote_col}")

    pts = df.dropna(subset=["lat", "lon"]).copy()
    pts["lat"], pts["lon"] = pts["lat"].astype(float), pts["lon"].astype(float)
    gdf = gpd.GeoDataFrame(
        pts, geometry=gpd.points_from_xy(pts["lon"], pts["lat"]), crs="EPSG:4326"
    ).to_crs(layer_crs)

    # lê apenas os lotes na área dos pontos (a camada inteira tem ~1,5 milhão de lotes)
    minx, miny, maxx, maxy = gdf.total_bounds
    pad = max_dist_m + 50
    lotes = gpd.read_file(lotes_path, bbox=(minx - pad, miny - pad, maxx + pad, maxy + pad))
    lotes = lotes[[setor_col, quadra_col, lote_col, "geometry"]].copy()
    print(f"Lotes carregados na área: {len(lotes)}")

    def sql10(r) -> str:
        return (str(r[setor_col]).split(".")[0].zfill(3)
                + str(r[quadra_col]).split(".")[0].zfill(3)
                + str(r[lote_col]).split(".")[0].zfill(4))
    lotes["sql_lote_10"] = lotes.apply(sql10, axis=1)
    lotes = lotes[["sql_lote_10", "geometry"]]

    inside = gpd.sjoin(gdf, lotes, how="left", predicate="within").drop(columns="index_right")
    inside = inside[~inside.index.duplicated(keep="first")]
    inside["sql_match"] = inside["sql_lote_10"].notna().map({True: "dentro_do_lote", False: ""})
    inside["sql_distancia_m"] = inside["sql_lote_10"].notna().map({True: 0.0, False: pd.NA})

    miss = inside[inside["sql_lote_10"].isna()].drop(columns=["sql_lote_10", "sql_match", "sql_distancia_m"])
    if len(miss):
        near = gpd.sjoin_nearest(miss, lotes, how="left", max_distance=max_dist_m,
                                 distance_col="sql_distancia_m").drop(columns="index_right")
        near = near[~near.index.duplicated(keep="first")]
        ok = near["sql_lote_10"].notna()
        inside.loc[near.index[ok], "sql_lote_10"] = near.loc[ok, "sql_lote_10"]
        inside.loc[near.index[ok], "sql_distancia_m"] = near.loc[ok, "sql_distancia_m"]
        inside.loc[near.index[ok], "sql_match"] = f"proximo_ate_{int(max_dist_m)}m"

    out = df.merge(
        pd.DataFrame(inside.drop(columns="geometry"))[["n_do_imovel", "sql_lote_10", "sql_match", "sql_distancia_m"]],
        on="n_do_imovel", how="left",
    )
    out["sql_iptu"] = out["sql_lote_10"]
    return out


# ───────────────────────── main ─────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--output", type=Path, default=Path("dados/caixa_sp_validacao_sql.csv"))
    ap.add_argument("--lotes", type=Path, help="camada de lotes do GeoSampa (.shp/.gpkg/.geojson)")
    ap.add_argument("--setor-col"); ap.add_argument("--quadra-col"); ap.add_argument("--lote-col")
    ap.add_argument("--max-dist-m", type=float, default=30.0, help="tolerância para ponto fora do lote")
    ap.add_argument("--max-geocode", type=int, default=400, help="máx. de chamadas ao Nominatim por execução")
    ap.add_argument("--area-max", type=float, default=500.0)
    ap.add_argument("--m2-min", type=float, default=1500.0)
    ap.add_argument("--m2-max", type=float, default=30000.0)
    ap.add_argument("--drop-flagged", action="store_true", help="remove linhas com flag_qualidade")
    args = ap.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(args.input, encoding="utf-8-sig")
    df = clean(df, args.area_max, args.m2_min, args.m2_max)
    print(f"Registros: {len(df)} | prédios distintos: {df['predio_id'].nunique()} "
          f"| sinalizados: {(df['flag_qualidade'] != '').sum()}")

    df = geocode_buildings(df, args.output.with_suffix(".geocache.json"), args.max_geocode)
    print(f"Com coordenadas: {df['lat'].notna().sum()} de {len(df)}")

    if args.lotes:
        df = join_lotes(df, args.lotes, args.setor_col, args.quadra_col, args.lote_col, args.max_dist_m)
        print("Resultado do cruzamento:\n", df["sql_match"].fillna("sem_coordenada").replace("", "sem_lote")
              .value_counts().to_string())

    if args.drop_flagged:
        df = df[df["flag_qualidade"] == ""]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False, encoding="utf-8-sig")
    print(f"Salvo em: {args.output}")


if __name__ == "__main__":
    main()