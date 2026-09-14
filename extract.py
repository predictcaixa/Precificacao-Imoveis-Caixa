from __future__ import annotations

import argparse
import json
import re
from typing import Iterable

import pandas as pd
import requests
from playwright.sync_api import sync_playwright

IBGE_BASE = "https://servicodados.ibge.gov.br/api/v1"
DEFAULT_ZAP_URL = "https://www.zapimoveis.com.br/aluguel/apartamentos/sao-paulo-sp/"


def fetch_json(url: str, timeout: int = 30) -> dict | list:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()


def fetch_municipio_data(codigo_municipio: int) -> dict:
    url = f"{IBGE_BASE}/localidades/municipios/{codigo_municipio}"
    return fetch_json(url)


def fetch_estado_data(codigo_estado: int) -> dict:
    url = f"{IBGE_BASE}/localidades/estados/{codigo_estado}"
    return fetch_json(url)


def fetch_ibge_cidades(cidades: list[str] | None = None) -> pd.DataFrame:
    cidades_map = {
        "Joinville": 4209102,
        "Curitiba": 4106902,
        "Florianópolis": 4205407,
        "São Paulo": 3550308,
    }

    if cidades is None:
        cidades = list(cidades_map.keys())

    rows: list[dict] = []
    for nome in cidades:
        codigo = cidades_map.get(nome)
        if codigo is None:
            continue
        municipio = fetch_municipio_data(codigo)
        uf = municipio.get("microrregiao", {}).get("mesorregiao", {}).get("UF", {})
        rows.append(
            {
                "cidade": nome,
                "codigo_ibge": municipio.get("id"),
                "nome_municipio": municipio.get("nome"),
                "uf": uf.get("sigla"),
                "estado": uf.get("nome"),
                "regiao": municipio.get("regiao", {}).get("nome"),
            }
        )

    df = pd.DataFrame(rows)
    return df


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def parse_price(value: str) -> float | None:
    if not value:
        return None
    cleaned = re.sub(r"[^0-9,\.]+", "", value.replace(".", "").replace(",", "."))
    if not cleaned:
        return None
    return float(cleaned)


def parse_listing_text(text: str) -> dict:
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return {}

    price = re.search(r"R\$\s*([0-9.]+(?:,[0-9]{2})?)", clean)
    area = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:m²|m2)", clean, flags=re.IGNORECASE)
    quartos = re.search(r"(?:Quantidade de )?Quartos?\s*(?:[:\-])?\s*(\d+)", clean, flags=re.IGNORECASE)
    banheiros = re.search(r"(?:Quantidade de )?Banheiros?\s*(?:[:\-])?\s*(\d+)", clean, flags=re.IGNORECASE)
    vagas = re.search(r"(?:Quantidade de )?Vagas?(?: de garagem)?\s*(?:[:\-])?\s*(\d+)", clean, flags=re.IGNORECASE)

    bairro = None
    for marker in ["Barra Funda", "Butantã", "Centro", "Pinheiros", "Moema", "Jardins", "Tatuapé", "Vila Mariana", "Santa Cecília", "Sé"]:
        if marker.lower() in clean.lower():
            bairro = marker
            break

    if not bairro:
        match = re.search(r"([A-Z][A-Za-zÀ-ÿ\- ]+),\s*São Paulo", clean)
        if match:
            bairro = match.group(1).strip()

    return {
        "cidade": "São Paulo",
        "bairro": bairro,
        "preco": parse_price(price.group(0)) if price else None,
        "area_m2": float(area.group(1).replace(",", ".")) if area else None,
        "quartos": int(quartos.group(1)) if quartos else None,
        "banheiros": int(banheiros.group(1)) if banheiros else None,
        "vagas": int(vagas.group(1)) if vagas else None,
        "texto_bruto": clean,
    }


def extract_cards_from_page(page) -> list[dict]:
    cards = page.locator('a[href*="/imovel/"]').all()[:15]
    rows: list[dict] = []
    for card in cards:
        text = card.inner_text()
        clean = re.sub(r"\s+", " ", text).strip()
        if len(clean) < 30:
            continue
        parsed = parse_listing_text(clean)
        if parsed.get("preco") or parsed.get("area_m2"):
            rows.append(parsed)
    return rows


def scrape_sao_paulo_imoveis(url: str = DEFAULT_ZAP_URL, max_cards: int = 15) -> pd.DataFrame:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 2200})
        page.goto(url, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(7000)

        texts = page.evaluate(
            """
            (limit) => {
                const cards = Array.from(document.querySelectorAll('a[href*="/imovel/"]'))
                    .slice(0, limit)
                    .map((el) => (el.innerText || '').replace(/\s+/g, ' ').trim())
                    .filter((text) => text && text.length > 30);
                return cards;
            }
            """,
            max_cards,
        )

        rows = []
        for text in texts:
            parsed = parse_listing_text(text)
            if parsed.get("preco") or parsed.get("area_m2"):
                rows.append(parsed)

        browser.close()

    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame([
            {"cidade": "São Paulo", "bairro": None, "preco": None, "area_m2": None, "quartos": None, "banheiros": None, "vagas": None, "texto_bruto": ""}
        ])
    return df


def merge_dataframes(left_rows: Iterable[dict], right_rows: Iterable[dict], left_key: str, right_key: str) -> pd.DataFrame:
    left_df = pd.DataFrame(list(left_rows))
    right_df = pd.DataFrame(list(right_rows))

    left_lookup = {normalize_key(column): column for column in left_df.columns}
    right_lookup = {normalize_key(column): column for column in right_df.columns}

    left_name = left_lookup.get(normalize_key(left_key), left_key)
    right_name = right_lookup.get(normalize_key(right_key), right_key)

    if left_name not in left_df.columns:
        raise KeyError(f"Chave não encontrada no dataframe da esquerda: {left_key}")
    if right_name not in right_df.columns:
        raise KeyError(f"Chave não encontrada no dataframe da direita: {right_key}")

    return left_df.merge(right_df, left_on=left_name, right_on=right_name, how="left")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extrai dados de imóveis de São Paulo como referência para o modelo de precificação.")
    parser.add_argument("--url", type=str, default=DEFAULT_ZAP_URL, help="URL da página de imóveis em São Paulo")
    parser.add_argument("--output", type=str, default="dados_sp.csv", help="Caminho do CSV final")
    parser.add_argument("--max-cards", type=int, default=15, help="Máximo de anúncios para coletar")
    args = parser.parse_args()

    df = scrape_sao_paulo_imoveis(url=args.url, max_cards=args.max_cards)
    df.to_csv(args.output, index=False, encoding="utf-8-sig")
    print(f"Arquivo salvo em: {args.output}")
    print(df.head().to_string(index=False))


if __name__ == "__main__":
    main()
