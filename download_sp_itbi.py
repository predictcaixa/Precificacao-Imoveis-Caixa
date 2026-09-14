from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright

PAGE_URL = "https://prefeitura.sp.gov.br/web/fazenda/w/acesso_a_informacao/31501"
DEFAULT_PATTERNS = [
    "GUIAS-DE-ITBI-PAGAS-2024",
    "GUIAS DE ITBI PAGAS 2024",
    "GUIAS_DE_ITBI_PAGAS_2024",
    "GUIAS-DE-ITBI-PAGAS-2023",
    "GUIAS DE ITBI PAGAS 2023",
]


def normalize_column_name(name: object) -> str:
    text = str(name).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def find_itbi_link(page, patterns: list[str]):
    for pattern in patterns:
        locator = page.locator(f'a[href*="{pattern}"]').first
        if locator.count() > 0:
            return locator

    for locator in page.locator('a[href]').all():
        href = locator.get_attribute("href") or ""
        lowered = href.lower()
        if any(token in lowered for token in ("itbi", "xlsx", "ods")) and any(year in lowered for year in ("2024", "2023", "2022")):
            return locator

    return None


def download_itbi_xlsx(download_dir: str | Path, patterns: list[str] | None = None) -> Path:
    patterns = patterns or DEFAULT_PATTERNS
    download_dir = Path(download_dir)
    download_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 2000})
        page.goto(PAGE_URL, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(8000)

        link = find_itbi_link(page, patterns)
        if link is None:
            raise RuntimeError("Não foi possível localizar o arquivo de ITBI da Prefeitura de São Paulo.")

        with page.expect_download() as download_info:
            link.click()

        downloaded = download_info.value
        final_path = download_dir / downloaded.suggested_filename
        downloaded.save_as(final_path)
        browser.close()

    return final_path


def build_csv_from_itbi(xlsx_path: str | Path, output_csv: str | Path) -> Path:
    df = pd.read_excel(xlsx_path)
    df.columns = [normalize_column_name(col) for col in df.columns]
    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False, encoding="utf-8-sig")
    return output_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Baixa os dados oficiais de ITBI da Prefeitura de São Paulo e salva em CSV.")
    parser.add_argument("--download-dir", type=str, default="dados_oficiais_sp", help="Pasta para guardar o arquivo Excel baixado")
    parser.add_argument("--output", type=str, default="dados_itbi_sp.csv", help="Caminho do CSV final")
    args = parser.parse_args()

    xlsx_path = download_itbi_xlsx(args.download_dir)
    csv_path = build_csv_from_itbi(xlsx_path, args.output)

    print(f"Arquivo Excel baixado: {xlsx_path}")
    print(f"Arquivo CSV salvo: {csv_path}")

    df = pd.read_csv(csv_path)
    print(df.head().to_string(index=False))


if __name__ == "__main__":
    main()
