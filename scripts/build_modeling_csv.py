"""Build a traceable, provisional CSV dataset from local source workbooks."""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from collections import defaultdict
from pathlib import Path

if __package__:
    from .audit_data_sources import (
        DATA_DIR,
        ENRICHED_FILE,
        ENRICHED_SHEET,
        JOIN_FIELDS,
        OFFICIAL_FILE,
        OFFICIAL_SHEET,
        _excel_serial_date,
        iter_xlsx_rows,
        normalize_value,
    )
else:
    from audit_data_sources import (
        DATA_DIR,
        ENRICHED_FILE,
        ENRICHED_SHEET,
        JOIN_FIELDS,
        OFFICIAL_FILE,
        OFFICIAL_SHEET,
        _excel_serial_date,
        iter_xlsx_rows,
        normalize_value,
    )


DEFAULT_DATASET = DATA_DIR / "derivados" / "avm_dataset_provisorio.csv"
DEFAULT_DICTIONARY = DATA_DIR / "derivados" / "avm_dicionario_provisorio.csv"

OUTPUT_FIELDS = (
    "record_id",
    "source_enriched_file",
    "source_enriched_sheet",
    "source_enriched_row",
    "source_official_file",
    "source_official_sheet",
    "source_official_rows",
    "link_status",
    "model_training_eligible",
    "selected_target_type",
    "selected_target_value_brl",
    "target_decision_status",
    "sql_grouping_id",
    "transaction_date",
    "transaction_nature",
    "transferred_share_percent",
    "itbi_declared_transaction_brl",
    "enriched_declared_transaction_brl",
    "candidate_total_value_brl",
    "candidate_total_origin_check",
    "candidate_unit_value_brl",
    "reference_tax_value_brl",
    "reference_tax_value_proportional_brl",
    "tax_base_value_brl",
    "financing_type",
    "financed_value_brl",
    "postal_code",
    "region_raw_unverified",
    "district_raw_unverified",
    "condominium_name_raw_unverified",
    "latitude_raw_unverified",
    "longitude_raw_unverified",
    "census_sector_2022_raw_unverified",
    "census_median_income_2022_brl_raw_unverified",
    "census_mean_income_2022_brl_raw_unverified",
    "land_area_cadastral_m2",
    "frontage_m",
    "ideal_fraction",
    "built_area_iptu_m2",
    "enriched_total_area_m2_raw_unverified",
    "private_area_m2_raw_unverified",
    "iptu_use_code",
    "iptu_use_description",
    "iptu_pattern_code",
    "iptu_pattern_description",
    "iptu_acc_construction_year",
    "enriched_age_years_calculated",
    "bedrooms_raw_unverified",
    "bathrooms_raw_unverified",
    "parking_spaces_raw_unverified",
    "elevator_building_raw_unverified",
    "unit_attribute_evidence_status",
    "building_attribute_evidence_status",
)

ENRICHED_TO_OUTPUT = {
    "N° do Cadastro (SQL)": "sql_grouping_id",
    "CEP": "postal_code",
    "Região": "region_raw_unverified",
    "Distrito": "district_raw_unverified",
    "COND": "condominium_name_raw_unverified",
    "LATITUDE": "latitude_raw_unverified",
    "LONGITUDE": "longitude_raw_unverified",
    "SETOR CENSITÁRIO 2022": "census_sector_2022_raw_unverified",
    "RENDA MEDIANA IBGE 2022 (R$)": "census_median_income_2022_brl_raw_unverified",
    "RENDA MÉDIA IBGE 2022 (R$)": "census_mean_income_2022_brl_raw_unverified",
    "Valor de Transação (declarado pelo contribuinte)": "enriched_declared_transaction_brl",
    "Área total": "enriched_total_area_m2_raw_unverified",
    "ÁREA PRIVATIVA (m²)": "private_area_m2_raw_unverified",
    "IDADE": "enriched_age_years_calculated",
    "QUARTOS": "bedrooms_raw_unverified",
    "BANHEIROS": "bathrooms_raw_unverified",
    "VAGAS": "parking_spaces_raw_unverified",
    "ELEVADOR": "elevator_building_raw_unverified",
    "Valor Total.": "candidate_total_value_brl",
    "Valor Unit.": "candidate_unit_value_brl",
}

OFFICIAL_TO_OUTPUT = {
    "Natureza de Transação": "transaction_nature",
    "Proporção Transmitida (%)": "transferred_share_percent",
    "Valor de Transação (declarado pelo contribuinte)": "itbi_declared_transaction_brl",
    "Valor Venal de Referência": "reference_tax_value_brl",
    "Valor Venal de Referência (proporcional)": "reference_tax_value_proportional_brl",
    "Base de Cálculo adotada": "tax_base_value_brl",
    "Tipo de Financiamento": "financing_type",
    "Valor Financiado": "financed_value_brl",
    "Área do Terreno (m2)": "land_area_cadastral_m2",
    "Testada (m)": "frontage_m",
    "Fração Ideal": "ideal_fraction",
    "Área Construída (m2)": "built_area_iptu_m2",
    "Uso (IPTU)": "iptu_use_code",
    "Descrição do uso (IPTU)": "iptu_use_description",
    "Padrão (IPTU)": "iptu_pattern_code",
    "Descrição do padrão (IPTU)": "iptu_pattern_description",
    "ACC (IPTU)": "iptu_acc_construction_year",
    "CEP": "postal_code",
}

DICTIONARY = {
    "record_id": ("Identificador hash da linha; não é identificador do imóvel.", "gerado", "registro", "observed_source_link", "Somente rastreabilidade; não usar como preditor."),
    "source_enriched_file": ("Nome do arquivo enriquecido de origem.", "22.10.2026.xlsx", "registro", "source_metadata", "Auditoria e reprodução."),
    "source_enriched_sheet": ("Aba de origem na planilha enriquecida.", "9662 DADOS", "registro", "source_metadata", "Auditoria e reprodução."),
    "source_enriched_row": ("Número da linha de origem na planilha enriquecida.", "22.10.2026.xlsx", "registro", "source_metadata", "Auditoria e reprodução."),
    "source_official_file": ("Arquivo municipal que pode complementar o registro.", "1. APARTAMENTOS.xlsx", "registro", "source_metadata", "Auditoria e reprodução."),
    "source_official_sheet": ("Aba municipal de ITBI usada no vínculo.", "2026", "registro", "source_metadata", "Auditoria e reprodução."),
    "source_official_rows": ("Linhas municipais encontradas pela chave composta; vazio quando não há vínculo único.", "ITBI/PMSP", "registro", "join_result", "Revisar ambiguidades, não deduplicar automaticamente."),
    "link_status": ("Resultado da associação por SQL + data + valor declarado.", "chave composta entre planilhas", "registro/transação", "validated_join_status", "Treino somente após resolução da ambiguidade e revisão da chave."),
    "model_training_eligible": ("Bloqueio explícito enquanto alvo e atributos não forem aprovados.", "regra do pipeline", "governança", "calculated_control", "Permanece false neste CSV."),
    "selected_target_type": ("Tipo de alvo definido pelo utilizador: valor de avaliação.", "definição do utilizador; conceito operacional requer confirmação CAIXA", "alvo", "user_defined_target_type", "O tipo foi definido; faltam valores de avaliação rastreáveis."),
    "selected_target_value_brl": ("Valor de avaliação do imóvel na data da avaliação; não localizado nas fontes atuais.", "não identificado nos arquivos locais nem em fonte pública unitária consultada", "R$", "absent_evaluation_labels", "Não substituir por ITBI, valor venal, base fiscal ou preço de oferta."),
    "target_decision_status": ("Tipo de alvo definido; origem dos rótulos de avaliação ainda ausente.", "definição do utilizador + auditoria dos arquivos", "governança", "target_type_set_label_source_missing", "Obter avaliações reais autorizadas com data, base de valor e unidade identificada."),
    "sql_grouping_id": ("SQL municipal, mantido apenas para rastreabilidade/agrupamento.", "PMSP/enriquecida", "cadastro", "source_observed", "Não usar como feature; considerar identificador para partição por imóvel."),
    "transaction_date": ("Data do evento ITBI ou data original da planilha enriquecida.", "ITBI/PMSP e planilha enriquecida", "data", "source_observed", "Validar natureza/status do evento e referência temporal."),
    "transaction_nature": ("Natureza administrativa informada no ITBI.", "ITBI/PMSP", "transação", "source_observed_for_unique_link", "Aplicar regra de elegibilidade aprovada."),
    "transferred_share_percent": ("Percentual transmitido no registro ITBI.", "ITBI/PMSP", "%", "source_observed_for_unique_link", "Definir tratamento de transmissão parcial."),
    "itbi_declared_transaction_brl": ("Valor de transação declarado pelo contribuinte no ITBI.", "ITBI/PMSP", "R$", "source_observed_for_unique_link", "Candidato a alvo de transação; não é automaticamente valor de mercado."),
    "enriched_declared_transaction_brl": ("Valor declarado transcrito na planilha enriquecida.", "22.10.2026.xlsx", "R$", "source_observed_unverified_copy", "Comparar com ITBI vinculado; não substituir o valor municipal."),
    "candidate_total_value_brl": ("Campo Valor Total da planilha enriquecida; coincide exatamente com Base de Cálculo adotada do ITBI nos 9.658 vínculos únicos.", "22.10.2026.xlsx + ITBI/PMSP", "R$", "matches_fiscal_itbi_base", "Tratar como valor fiscal nos vínculos confirmados; excluir do alvo de avaliação."),
    "candidate_total_origin_check": ("Comparação do Valor Total enriquecido com a Base de Cálculo adotada do ITBI.", "auditoria de correspondência local", "categoria", "measured_exact_match_on_unique_links", "A igualdade identifica a origem fiscal, não uma avaliação imobiliária."),
    "candidate_unit_value_brl": ("Campo Valor Unit da planilha enriquecida; coincide com total/área privativa.", "22.10.2026.xlsx", "R$/m²", "source_unverified_candidate_target", "Não usar como feature quando total for alvo; risco de vazamento/circularidade."),
    "reference_tax_value_brl": ("Valor venal de referência municipal.", "ITBI/PMSP", "R$", "source_observed_for_unique_link", "Valor fiscal separado do alvo."),
    "reference_tax_value_proportional_brl": ("Valor venal de referência proporcional.", "ITBI/PMSP", "R$", "source_observed_for_unique_link", "Valor fiscal separado do alvo."),
    "tax_base_value_brl": ("Base de cálculo fiscal do ITBI.", "ITBI/PMSP", "R$", "source_observed_for_unique_link", "Não confundir com valor declarado nem valor de avaliação."),
    "financing_type": ("Tipo de financiamento registrado no ITBI, quando informado.", "ITBI/PMSP", "categoria", "source_observed_for_unique_link", "Avaliar se está disponível e temporalmente apropriado na operação."),
    "financed_value_brl": ("Valor financiado registrado no ITBI.", "ITBI/PMSP", "R$", "source_observed_for_unique_link", "Não usar sem confirmar disponibilidade no momento da predição."),
    "postal_code": ("CEP informado na fonte municipal/enriquecida.", "PMSP", "CEP", "source_observed", "A validação da chave geográfica ainda é necessária."),
    "region_raw_unverified": ("Região da planilha enriquecida, linhagem não confirmada.", "22.10.2026.xlsx", "categoria", "unverified", "Não usar antes de validar definição e reprodução operacional."),
    "district_raw_unverified": ("Distrito informado na planilha enriquecida.", "22.10.2026.xlsx", "categoria", "unverified", "Validar contra referência territorial oficial."),
    "condominium_name_raw_unverified": ("Nome/descrição de condomínio da planilha enriquecida.", "22.10.2026.xlsx", "texto", "unverified_building_linkage", "Não usar como atributo da unidade; validar identidade do edifício."),
    "latitude_raw_unverified": ("Latitude da planilha enriquecida.", "22.10.2026.xlsx", "graus", "unverified_geocode", "Validar posição e compatibilidade com operação."),
    "longitude_raw_unverified": ("Longitude da planilha enriquecida.", "22.10.2026.xlsx", "graus", "unverified_geocode", "Validar posição e compatibilidade com operação."),
    "census_sector_2022_raw_unverified": ("Código de setor censitário da versão 2022.", "22.10.2026.xlsx/IBGE", "código", "unverified_linkage", "Validar método de junção espacial e versão do setor."),
    "census_median_income_2022_brl_raw_unverified": ("Renda mediana territorial atribuída ao setor censitário.", "22.10.2026.xlsx/IBGE", "R$", "unverified_aggregate", "Contexto territorial, não renda do imóvel/morador."),
    "census_mean_income_2022_brl_raw_unverified": ("Renda média territorial atribuída ao setor censitário.", "22.10.2026.xlsx/IBGE", "R$", "unverified_aggregate", "Contexto territorial, não renda do imóvel/morador."),
    "land_area_cadastral_m2": ("Área do terreno no cadastro municipal.", "ITBI/PMSP", "m²", "source_observed_for_unique_link", "Não substituir por área da unidade."),
    "frontage_m": ("Testada cadastral do terreno.", "ITBI/PMSP", "m", "source_observed_for_unique_link", "Atributo do lote; avaliar aderência para apartamento."),
    "ideal_fraction": ("Fração ideal cadastrada para o imóvel.", "ITBI/PMSP", "fração", "source_observed_for_unique_link", "Confirmar escala/definição e utilidade para tipologia."),
    "built_area_iptu_m2": ("Área construída do cadastro IPTU.", "ITBI/PMSP", "m²", "source_observed_for_unique_link", "Não equivale automaticamente à área privativa ou total."),
    "enriched_total_area_m2_raw_unverified": ("Campo Área total da planilha enriquecida; coincide com área construída ITBI em 9.655/9.658 vínculos únicos.", "22.10.2026.xlsx", "m²", "unverified_semantics", "Preservar nome original; definir com documentação antes de mapear."),
    "private_area_m2_raw_unverified": ("Área privativa transcrita na planilha enriquecida.", "22.10.2026.xlsx", "m²", "unverified_source", "Exigir documento da mesma unidade; 89 inconsistências lógicas com Área total."),
    "iptu_use_code": ("Código de uso IPTU.", "ITBI/PMSP", "código", "source_observed_for_unique_link", "Manter código/descrição da PMSP; não equivale a padrão IBAPE."),
    "iptu_use_description": ("Descrição municipal do uso IPTU.", "ITBI/PMSP", "texto", "source_observed_for_unique_link", "Preservar descrição e versão do dicionário."),
    "iptu_pattern_code": ("Código de padrão cadastral IPTU.", "ITBI/PMSP", "código", "source_observed_for_unique_link", "Não mapear para IUP/IBAPE sem validação técnica."),
    "iptu_pattern_description": ("Descrição municipal do padrão IPTU.", "ITBI/PMSP", "texto", "source_observed_for_unique_link", "Preservar a classificação original."),
    "iptu_acc_construction_year": ("ACC/IPTU, ano de término de construção cadastral corrigido.", "ITBI/PMSP", "ano", "source_observed_for_unique_link", "Diverge em 51/9.658 vínculos únicos; revisar."),
    "enriched_age_years_calculated": ("Idade calculada como 2026 menos ACC/IPTU na planilha enriquecida.", "22.10.2026.xlsx", "anos", "calculated_not_independent", "Guardar data-base; não representa conservação/idade estimada IBAPE."),
    "bedrooms_raw_unverified": ("Quantidade de quartos da planilha enriquecida.", "22.10.2026.xlsx", "contagem", "unverified_unit_attribute", "Não inferir por área; obter evidência da própria unidade."),
    "bathrooms_raw_unverified": ("Quantidade de banheiros da planilha enriquecida.", "22.10.2026.xlsx", "contagem", "unverified_unit_attribute", "Definir inclusão de lavabo/banheiro de serviço e validar por unidade."),
    "parking_spaces_raw_unverified": ("Quantidade de vagas da planilha enriquecida.", "22.10.2026.xlsx", "contagem", "unverified_unit_attribute", "Confirmar vínculo jurídico/físico com a unidade."),
    "elevator_building_raw_unverified": ("Indicador de elevador associado presumivelmente ao edifício.", "22.10.2026.xlsx", "booleano/categoria", "unverified_building_attribute", "Validar por edifício e manter separado da unidade."),
    "unit_attribute_evidence_status": ("Status de evidência de quartos, banheiros, vagas e áreas de unidade.", "auditoria da proveniência disponível", "categoria", "unverified", "Todos os atributos da unidade ficam fora do modelo inicial."),
    "building_attribute_evidence_status": ("Status de evidência de elevador/condomínio.", "auditoria da proveniência disponível", "categoria", "unverified", "Não usar até validar associação e atualização."),
}


def _transaction_key(row: dict[str, str], *, enriched: bool) -> tuple[str, ...]:
    key_index = 2 if enriched else 1
    return tuple(
        normalize_value(row.get(field[key_index], ""), field[3])
        for field in JOIN_FIELDS
    )


def _iso_date(value: str) -> str:
    return _excel_serial_date(value) or value


def build_dataset(data_dir: Path = DATA_DIR) -> list[dict[str, str]]:
    official_path = data_dir / OFFICIAL_FILE
    enriched_path = data_dir / ENRICHED_FILE
    for path in (official_path, enriched_path):
        if not path.is_file():
            raise FileNotFoundError(f"Arquivo necessário não encontrado: {path}")

    official_by_key: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for official in iter_xlsx_rows(
        official_path, OFFICIAL_SHEET, include_source_row=True
    ):
        key = _transaction_key(official, enriched=False)
        if all(key):
            official_by_key[key].append(official)

    output_rows: list[dict[str, str]] = []
    for enriched in iter_xlsx_rows(
        enriched_path, ENRICHED_SHEET, include_source_row=True
    ):
        key = _transaction_key(enriched, enriched=True)
        matches = official_by_key.get(key, []) if all(key) else []
        if not matches:
            link_status = "unmatched"
            official = {}
        elif len(matches) == 1:
            link_status = "unique"
            official = matches[0]
        else:
            link_status = "ambiguous"
            official = {}

        source_row = enriched.get("_source_excel_row", "")
        digest = hashlib.sha256(
            ("|".join(key) + "|" + source_row).encode("utf-8")
        ).hexdigest()
        record = {field: "" for field in OUTPUT_FIELDS}
        record.update(
            {
                "record_id": digest,
                "source_enriched_file": ENRICHED_FILE,
                "source_enriched_sheet": ENRICHED_SHEET,
                "source_enriched_row": source_row,
                "source_official_file": OFFICIAL_FILE if matches else "",
                "source_official_sheet": OFFICIAL_SHEET if matches else "",
                "source_official_rows": ";".join(
                    item.get("_source_excel_row", "") for item in matches
                ),
                "link_status": link_status,
                "model_training_eligible": "false",
                "selected_target_type": "avaliacao",
                "selected_target_value_brl": "",
                "target_decision_status": (
                    "evaluation_target_set_by_user; "
                    "evaluation_values_not_identified"
                ),
                "sql_grouping_id": enriched.get("N° do Cadastro (SQL)", ""),
                "transaction_date": _iso_date(
                    enriched.get("Data de Transação", "")
                ),
                "unit_attribute_evidence_status": "unverified",
                "building_attribute_evidence_status": "unverified",
            }
        )

        for source_field, output_field in ENRICHED_TO_OUTPUT.items():
            record[output_field] = enriched.get(source_field, "")
        for source_field, output_field in OFFICIAL_TO_OUTPUT.items():
            if official:
                record[output_field] = official.get(source_field, "")
        if link_status == "unique":
            candidate_total = normalize_value(
                record["candidate_total_value_brl"], "number"
            )
            tax_base = normalize_value(record["tax_base_value_brl"], "number")
            record["candidate_total_origin_check"] = (
                "exact_match_itbi_tax_base"
                if candidate_total and candidate_total == tax_base
                else "does_not_match_itbi_tax_base"
            )
        elif link_status == "ambiguous":
            record["candidate_total_origin_check"] = (
                "ambiguous_itbi_link_not_assessed"
            )
        else:
            record["candidate_total_origin_check"] = (
                "no_itbi_link_not_assessed"
            )
        if official:
            record["transaction_date"] = _iso_date(
                official.get("Data de Transação", "")
            )
        record["enriched_age_years_calculated"] = enriched.get("IDADE", "")
        output_rows.append(record)
    return output_rows


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fieldnames, extrasaction="raise"
        )
        writer.writeheader()
        writer.writerows(rows)


def write_dictionary(
    path: Path, dataset_rows: list[dict[str, str]]
) -> None:
    total = len(dataset_rows)
    fields = [
        "column",
        "definition",
        "unit",
        "source",
        "scope",
        "classification",
        "nonempty_rows",
        "coverage_percent",
        "validation_status",
        "recommendation",
    ]
    rows = []
    for column in OUTPUT_FIELDS:
        definition, source, unit, classification, recommendation = DICTIONARY[column]
        nonempty = sum(bool(row.get(column, "").strip()) for row in dataset_rows)
        rows.append(
            {
                "column": column,
                "definition": definition,
                "unit": unit,
                "source": source,
                "scope": (
                    "unit"
                    if column in {
                        "private_area_m2_raw_unverified",
                        "bedrooms_raw_unverified",
                        "bathrooms_raw_unverified",
                        "parking_spaces_raw_unverified",
                    }
                    else "building"
                    if column in {
                        "condominium_name_raw_unverified",
                        "elevator_building_raw_unverified",
                    }
                    else "transaction"
                    if column in {
                        "transaction_date",
                        "transaction_nature",
                        "transferred_share_percent",
                        "itbi_declared_transaction_brl",
                        "enriched_declared_transaction_brl",
                    }
                    else "location"
                    if column in {
                        "postal_code",
                        "region_raw_unverified",
                        "district_raw_unverified",
                        "latitude_raw_unverified",
                        "longitude_raw_unverified",
                        "census_sector_2022_raw_unverified",
                        "census_median_income_2022_brl_raw_unverified",
                        "census_mean_income_2022_brl_raw_unverified",
                    }
                    else "record/administrative"
                ),
                "classification": classification,
                "nonempty_rows": nonempty,
                "coverage_percent": round(
                    nonempty * 100 / total, 2
                )
                if total
                else 0,
                "validation_status": (
                    "not_verified"
                    if "unverified" in classification
                    or classification.startswith("source_unverified")
                    or classification.startswith("absent")
                    or classification.startswith("pending")
                    else classification
                ),
                "recommendation": recommendation,
            }
        )
    _write_csv(path, fields, rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gera CSV consolidado provisório e dicionário de dados."
    )
    parser.add_argument(
        "--dataset-output",
        type=Path,
        default=DEFAULT_DATASET,
        help=f"CSV consolidado (padrão: {DEFAULT_DATASET})",
    )
    parser.add_argument(
        "--dictionary-output",
        type=Path,
        default=DEFAULT_DICTIONARY,
        help=f"CSV dicionário (padrão: {DEFAULT_DICTIONARY})",
    )
    args = parser.parse_args(argv)

    rows = build_dataset()
    _write_csv(args.dataset_output, list(OUTPUT_FIELDS), rows)
    write_dictionary(args.dictionary_output, rows)
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row["link_status"]] += 1
    print(
        f"Dataset: {args.dataset_output} ({len(rows)} linhas); "
        f"dicionário: {args.dictionary_output} ({len(OUTPUT_FIELDS)} campos)."
    )
    print(
        "Vínculos: "
        + ", ".join(f"{status}={counts[status]}" for status in sorted(counts))
    )
    print(
        "Treino elegível: 0; tipo de alvo definido: avaliação; "
        "rótulos de avaliação disponíveis: não."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
