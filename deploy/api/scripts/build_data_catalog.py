"""Build a provenance-aware inventory of the project data without moving originals."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__:
    from .audit_evaluation_csv import DEFAULT_INPUT as EVALUATIONS_INPUT
    from .audit_evaluation_csv import audit_csv as audit_evaluations
    from .audit_offer_csv import DEFAULT_INPUT as OFFERS_INPUT
    from .audit_offer_csv import audit_csv as audit_offers
    from .audit_caixa_validation import DEFAULT_INPUT as CAIXA_VALIDATION_INPUT
    from .audit_caixa_validation import audit_dataset as audit_caixa_validation
    from .validate_caixa_calculations import DEFAULT_OUTPUT as CAIXA_CALCULATION_CHECK
    from .validate_caixa_calculations import validate_report as validate_caixa_calculations
else:
    from audit_evaluation_csv import DEFAULT_INPUT as EVALUATIONS_INPUT
    from audit_evaluation_csv import audit_csv as audit_evaluations
    from audit_offer_csv import DEFAULT_INPUT as OFFERS_INPUT
    from audit_offer_csv import audit_csv as audit_offers
    from audit_caixa_validation import DEFAULT_INPUT as CAIXA_VALIDATION_INPUT
    from audit_caixa_validation import audit_dataset as audit_caixa_validation
    from validate_caixa_calculations import DEFAULT_OUTPUT as CAIXA_CALCULATION_CHECK
    from validate_caixa_calculations import validate_report as validate_caixa_calculations


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "dados"
DERIVED_DIR = DATA_DIR / "derivados"
DEFAULT_JSON = DERIVED_DIR / "catalogo_bases.json"
DEFAULT_MARKDOWN = BASE_DIR / "docs" / "catalogo_bases.md"

DATASETS: tuple[dict[str, Any], ...] = (
    {
        "id": "itbi_pmsp_transactions",
        "name": "Transações declaradas ITBI/PMSP",
        "path": "dados/1. APARTAMENTOS.xlsx",
        "data_kind": "transaction",
        "target": "Valor declarado pelo contribuinte em transação ITBI",
        "unit_of_analysis": "registro administrativo de transação/cadastro",
        "allowed_use": "referência experimental de transações e análise técnica",
        "training_role": "not_a_CAIXA_appraisal_target",
        "limitations": [
            "Valor declarado no ITBI não é automaticamente valor de avaliação.",
            "Área construída cadastral não equivale automaticamente à área privativa ou total.",
        ],
    },
    {
        "id": "enriched_workbook",
        "name": "Planilha enriquecida de imóveis",
        "path": "dados/22.10.2026.xlsx",
        "data_kind": "mixed_unverified_attributes",
        "target": None,
        "unit_of_analysis": "registro de imóvel/unidade a confirmar",
        "allowed_use": "auditoria de vínculo e investigação de proveniência",
        "training_role": "not_training_eligible_without_attribute_evidence",
        "limitations": [
            "Campos de área privativa, quartos, banheiros, vagas e elevador não têm proveniência validada.",
            "O preenchimento de uma célula não comprova evidência ou associação correta à unidade.",
        ],
    },
    {
        "id": "evaluation_labels",
        "name": "Rótulos de avaliações de mercado",
        "path": "dados/derivados/avaliacoes_imoveis_template.csv",
        "data_kind": "appraisal",
        "target": "valor de mercado avaliado em R$ na data-base da avaliação",
        "unit_of_analysis": "unidade residencial identificada por token pseudonimizado",
        "allowed_use": "entrada controlada para auditoria de avaliações autorizadas",
        "training_role": "blocked_until_expert_review_and_independent_validation",
        "limitations": [
            "A triagem de CSV não comprova autenticidade, autorização, representatividade ou qualidade profissional.",
            "O template vazio não é uma base de treinamento.",
        ],
    },
    {
        "id": "caixa_sp_validation_candidate",
        "name": "Lote CAIXA de avaliações para validação",
        "path": "scripts/dados/caixa_sp_validacao.csv",
        "data_kind": "caixa_appraisal_validation_candidate",
        "target": "Valor de avaliação CAIXA de imóvel retomado",
        "unit_of_analysis": "imóvel anunciado em retrato de coleta",
        "allowed_use": "auditoria de rótulos e benchmark espacial exploratório",
        "training_role": "candidate_labels_pending_expert_review",
        "limitations": [
            "Data da avaliação ausente no lote; não permite validação temporal.",
            "Autorização, metodologia, representatividade e identidade da unidade precisam de revisão.",
            "Preço de venda/desconto não pode ser confundido com o valor de avaliação.",
        ],
    },
    {
        "id": "caixa_calculation_verification",
        "name": "Verificação independente dos cálculos CAIXA",
        "path": "scripts/dados/caixa_sp_validacao_calculation_check.json",
        "data_kind": "calculation_verification",
        "target": None,
        "unit_of_analysis": "checagem agregada da auditoria",
        "allowed_use": "verificação reprodutível da aritmética e das métricas reportadas",
        "training_role": "not_training_data",
        "limitations": [
            "Verifica a implementação aritmética, não valida a origem ou qualidade dos rótulos.",
            "A simulação sintética não é evidência de desempenho de avaliação.",
        ],
    },
    {
        "id": "asking_price_offers",
        "name": "Ofertas imobiliárias",
        "path": "dados/derivados/ofertas_imoveis_template.csv",
        "data_kind": "asking_price_offer",
        "target": "preço pedido no anúncio na data/hora da captura",
        "unit_of_analysis": "anúncio de imóvel",
        "allowed_use": "auditoria de uma base de oferta separada, após confirmar direitos de uso",
        "training_role": "separate_target_not_appraisal",
        "limitations": [
            "Preço anunciado não é preço transacionado nem valor de avaliação.",
            "Amostra atual sem anúncios auditados.",
        ],
    },
    {
        "id": "provisional_join_dataset",
        "name": "Dataset provisório de auditoria e integração",
        "path": "dados/derivados/avm_dataset_provisorio.csv",
        "data_kind": "audit_join",
        "target": "nenhum rótulo de avaliação preenchido",
        "unit_of_analysis": "registro enriquecido associado a linha ITBI",
        "allowed_use": "rastreabilidade, conferência e revisão de atributos",
        "training_role": "blocked",
        "limitations": [
            "A elegibilidade de treino é false; não converter valores fiscais em avaliação.",
            "Atributos enriquecidos não validados permanecem apenas para investigação.",
        ],
    },
    {
        "id": "experimental_itbi_profile",
        "name": "Perfil do comparador experimental ITBI",
        "path": "models/itbi_reference_2026.json",
        "data_kind": "derived_transaction_reference",
        "target": "transação declarada ITBI",
        "unit_of_analysis": "perfil agregado de transações comparáveis",
        "allowed_use": "referência exploratória e backtest temporal ITBI",
        "training_role": "not_an_appraisal_model",
        "limitations": [
            "Backtest contra transações ITBI não mede erro de avaliações.",
            "Faixa P10-P90 observada não é intervalo de confiança individual.",
        ],
    },
    {
        "id": "experimental_itbi_transaction_model",
        "name": "Experimento de modelo para transações ITBI",
        "path": "models/itbi_transaction_experiment.json",
        "data_kind": "experimental_declared_transaction_model",
        "target": "Valor declarado pelo contribuinte em transação ITBI",
        "unit_of_analysis": "transação residencial elegível",
        "allowed_use": "benchmark técnico experimental contra transações ITBI",
        "training_role": "not_a_CAIXA_appraisal_model_or_operational_predictor",
        "limitations": [
            "As métricas avaliam somente a previsão de valor declarado ITBI.",
            "O holdout temporal não é validação independente de avaliações de mercado.",
            "O artefato não habilita treinamento de avaliação nem endpoints operacionais.",
        ],
    },
    {
        "id": "legacy_simulated_data",
        "name": "Dados legados derivados",
        "path": "dados/dados_sp_ref.csv",
        "data_kind": "legacy_derived",
        "target": "preço legado sem proveniência adequada",
        "unit_of_analysis": "registro sintético/derivado legado",
        "allowed_use": "quarentena e referência de auditoria histórica apenas",
        "training_role": "prohibited",
        "limitations": [
            "Atributos foram inferidos por área e o campo de área foi selecionado incorretamente no pipeline antigo.",
            "Não usar para treino, validação ou apresentação de métricas.",
        ],
    },
    {
        "id": "ibape_reference",
        "name": "Referência técnica IUP/IBAPE",
        "path": "dados/Padrão Construtivo - FOTOS e características das Edificações - IBAPE SP .pdf",
        "data_kind": "technical_reference",
        "target": None,
        "unit_of_analysis": "documento técnico",
        "allowed_use": "consulta metodológica dentro do escopo documentado",
        "training_role": "not_a_data_source",
        "limitations": [
            "Documento metodológico não contém rótulos de avaliação desta amostra.",
            "Adequação e autorização de uso no método final devem ser avaliadas pelos responsáveis técnicos.",
        ],
    },
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _row_count(path: Path) -> int | None:
    if path.suffix.casefold() != ".csv":
        return None
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return max(sum(1 for _ in csv.reader(handle)) - 1, 0)


def _file_metadata(relative_path: str) -> dict[str, Any]:
    path = BASE_DIR / Path(relative_path)
    if not path.is_file():
        return {
            "exists": False,
            "size_bytes": None,
            "sha256": None,
            "csv_data_rows": None,
        }
    return {
        "exists": True,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "csv_data_rows": _row_count(path),
    }


def build_catalog() -> dict[str, Any]:
    join_path = BASE_DIR / "docs" / "resultado_auditoria_vinculos.json"
    profile_path = BASE_DIR / "models" / "itbi_reference_2026.json"
    join_audit = json.loads(join_path.read_text(encoding="utf-8")) if join_path.is_file() else {}
    profile = json.loads(profile_path.read_text(encoding="utf-8")) if profile_path.is_file() else {}
    experiment_path = BASE_DIR / "models" / "itbi_transaction_experiment.json"
    experiment = (
        json.loads(experiment_path.read_text(encoding="utf-8"))
        if experiment_path.is_file()
        else {}
    )

    evaluation_audit = audit_evaluations(EVALUATIONS_INPUT)
    offer_audit = audit_offers(OFFERS_INPUT)
    caixa_validation_audit = audit_caixa_validation(CAIXA_VALIDATION_INPUT)
    calculation_check = validate_caixa_calculations(
        CAIXA_VALIDATION_INPUT, caixa_validation_audit
    )
    if calculation_check["status"] != "passed":
        failed_checks = [
            check["check"]
            for check in calculation_check["checks"]
            if not check["passed"]
        ]
        raise ValueError(
            "A verificação independente dos cálculos CAIXA falhou: "
            + ", ".join(failed_checks)
        )
    CAIXA_CALCULATION_CHECK.parent.mkdir(parents=True, exist_ok=True)
    CAIXA_CALCULATION_CHECK.write_text(
        json.dumps(calculation_check, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    entries: list[dict[str, Any]] = []

    for definition in DATASETS:
        entry = dict(definition)
        entry.update(_file_metadata(definition["path"]))
        if entry["id"] == "itbi_pmsp_transactions":
            entry["record_count"] = join_audit.get("inputs", {}).get("official_rows")
            entry["reference_period"] = profile.get("reference_period")
            entry["eligible_transaction_count"] = profile.get(
                "filter_counts", {}
            ).get("unique_eligible_transactions")
        elif entry["id"] == "enriched_workbook":
            entry["record_count"] = join_audit.get("inputs", {}).get("enriched_rows")
            entry["join_audit"] = join_audit.get("join")
        elif entry["id"] == "evaluation_labels":
            entry["record_count"] = evaluation_audit["row_count"]
            entry["audit_status"] = evaluation_audit
        elif entry["id"] == "caixa_sp_validation_candidate":
            entry["record_count"] = caixa_validation_audit["record_count"]
            entry["audit_status"] = caixa_validation_audit
        elif entry["id"] == "caixa_calculation_verification":
            entry["record_count"] = calculation_check["checks_passed"]
            entry["audit_status"] = calculation_check
        elif entry["id"] == "asking_price_offers":
            entry["record_count"] = offer_audit["row_count"]
            entry["audit_status"] = offer_audit
        elif entry["id"] == "provisional_join_dataset":
            entry["record_count"] = entry["csv_data_rows"]
        elif entry["id"] == "experimental_itbi_profile":
            entry["record_count"] = profile.get("filter_counts", {}).get(
                "unique_eligible_transactions"
            )
            entry["reference_period"] = profile.get("reference_period")
            entry["temporal_backtest"] = profile.get("temporal_backtest")
        elif entry["id"] == "experimental_itbi_transaction_model":
            entry["record_count"] = None
            entry["status"] = experiment.get("status")
            entry["model_id"] = experiment.get("model_id")
            entry["experiment_version"] = experiment.get("experiment_version")
            entry["training_policy"] = experiment.get("training_policy")
            entry["estimators"] = experiment.get("estimators")
            entry["target_quality"] = experiment.get("target_quality")
        elif entry["id"] == "legacy_simulated_data":
            entry["record_count"] = entry["csv_data_rows"]
        else:
            entry["record_count"] = None
        entries.append(entry)

    missing_sources = [entry["id"] for entry in entries if not entry["exists"]]
    summary = {
        "appraisal_target_selected": True,
        "appraisal_label_rows": evaluation_audit["row_count"],
        "appraisal_candidate_rows": evaluation_audit[
            "candidate_rows_for_expert_review"
        ],
        "caixa_appraisal_validation_rows": caixa_validation_audit["record_count"],
        "caixa_appraisal_spatial_candidate_rows": caixa_validation_audit[
            "candidate_rows_for_spatial_validation"
        ],
        "caixa_appraisal_date_coverage_percent": caixa_validation_audit[
            "quality"
        ]["appraisal_date_coverage_percent"],
        "caixa_appraisal_spatial_baseline_validation": caixa_validation_audit[
            "spatial_baseline_validation"
        ],
        "caixa_appraisal_feature_validation": caixa_validation_audit[
            "feature_incremental_validation"
        ],
        "caixa_appraisal_temporal_validation": caixa_validation_audit[
            "temporal_validation"
        ],
        "caixa_calculation_checks_passed": calculation_check["checks_passed"],
        "caixa_calculation_checks_failed": calculation_check["checks_failed"],
        "caixa_calculation_validation_status": calculation_check["status"],
        "caixa_appraisal_attribute_inventory": caixa_validation_audit[
            "attribute_inventory"
        ],
        "offer_rows": offer_audit["row_count"],
        "itbi_eligible_transactions": profile.get("filter_counts", {}).get(
            "unique_eligible_transactions"
        ),
        "itbi_experiment_training_rows": experiment.get(
            "training_policy", {}
        ).get("training_rows"),
        "itbi_experiment_test_rows": experiment.get(
            "training_policy", {}
        ).get("test_rows"),
        "itbi_experiment_estimators": experiment.get("estimators"),
        "itbi_experiment_target_quality": experiment.get("target_quality"),
        "enriched_join_unique": join_audit.get("join", {}).get(
            "matched_unique_rows"
        ),
        "enriched_join_ambiguous": join_audit.get("join", {}).get(
            "matched_ambiguous_rows"
        ),
        "training_enabled": False,
        "missing_catalog_sources": missing_sources,
    }
    return {
        "catalog_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": (
            "Inventory and separate datasets by semantic target; this catalog "
            "does not approve a source or enable model training."
        ),
        "summary": summary,
        "datasets": entries,
        "governance": {
            "target_selected": "market appraisal value",
            "do_not_mix": [
                "appraisal",
                "ITBI_declared_transaction",
                "asking_price_offer",
                "tax_reference_or_tax_base",
            ],
            "training_release": (
                "Requires evidence/legal review, expert review, representativeness, "
                "independent validation, operational feature compatibility, and a "
                "separate approval. No dataset is released automatically."
            ),
        },
    }


def render_markdown(catalog: dict[str, Any]) -> str:
    summary = catalog["summary"]
    lines = [
        "# Catálogo e organização das bases",
        "",
        f"**Gerado em UTC:** {catalog['generated_at_utc']}",
        "",
        "> O catálogo organiza os arquivos sem mover ou alterar as fontes originais. A classificação documenta uso e limitações; não representa aprovação de dados nem liberação de treinamento.",
        "",
        "## Resumo atual",
        "",
        "| Indicador | Resultado |",
        "|---|---:|",
        f"| Avaliações de mercado no template | {summary['appraisal_label_rows']} |",
        f"| Avaliações candidatas à revisão técnica | {summary['appraisal_candidate_rows']} |",
        f"| Lote CAIXA: linhas / candidatas à validação espacial | "
        f"{summary['caixa_appraisal_validation_rows']} / "
        f"{summary['caixa_appraisal_spatial_candidate_rows']} |",
        f"| Cobertura da data de avaliação CAIXA | "
        f"{summary['caixa_appraisal_date_coverage_percent']:.1f}% |",
        f"| Validação temporal CAIXA | "
        f"{summary['caixa_appraisal_temporal_validation']['status']} |",
        f"| Verificação independente dos cálculos | "
        f"{summary['caixa_calculation_checks_passed']} aprovados / "
        f"{summary['caixa_calculation_checks_failed']} falhas |",
        f"| Anúncios no template auditado | {summary['offer_rows']} |",
        f"| Transações ITBI elegíveis | {summary['itbi_eligible_transactions']} |",
        f"| Experimento ITBI: treino / teste | "
        f"{summary['itbi_experiment_training_rows'] or 'ND'} / "
        f"{summary['itbi_experiment_test_rows'] or 'ND'} |",
        f"| Ligações enriquecidas únicas | {summary['enriched_join_unique']} |",
        f"| Ligações enriquecidas ambíguas | {summary['enriched_join_ambiguous']} |",
        "| Treinamento liberado | Não |",
        "",
        "## Bases classificadas",
        "",
        "| Base | Arquivo | Natureza/alvo | Registros | Uso permitido agora | Elegibilidade para treino |",
        "|---|---|---|---:|---|---|",
    ]
    for entry in catalog["datasets"]:
        if not entry["exists"]:
            count = "arquivo ausente"
        elif entry.get("record_count") is None:
            count = "ND"
        else:
            count = str(entry["record_count"])
        lines.append(
            f"| {entry['name']} | `{entry['path']}` | {entry['data_kind']} / "
            f"{entry['target'] or 'sem alvo'} | {count} | {entry['allowed_use']} | "
            f"{entry['training_role']} |"
        )
    lines.extend(
        [
            "",
            "## Lote CAIXA de avaliações — validação exploratória",
            "",
            f"O arquivo `scripts/dados/caixa_sp_validacao.csv` contém "
            f"{summary['caixa_appraisal_validation_rows']} linhas; "
            f"{summary['caixa_appraisal_spatial_candidate_rows']} atendem aos filtros estruturais "
            "iniciais para benchmark espacial (apartamento, área privativa e alvo positivo). "
            f"A cobertura de `avaliacao_data` é {summary['caixa_appraisal_date_coverage_percent']:.1f}%. "
            f"A validação temporal está `"
            f"{summary['caixa_appraisal_temporal_validation']['status']}`; "
            "todos os rótulos continuam candidatos "
            "a revisão, sem liberação para treino ou operação.",
            "",
            "| Estimador-base | MAE (R$) | MdAPE | P90 APE | WAPE | R² |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    caixa_validation = summary["caixa_appraisal_spatial_baseline_validation"]
    if caixa_validation:
        for key in (
            "training_citywide_median",
            "training_median_per_m2_times_private_area",
        ):
            estimator = caixa_validation["estimators"][key]
            metrics = estimator["out_of_fold_metrics"]
            lines.append(
                f"| {estimator['description']} | {metrics['mae_brl']:.2f} | "
                f"{metrics['median_absolute_percentage_error_percent']:.2f}% | "
                f"{metrics['p90_absolute_percentage_error_percent']:.2f}% | "
                f"{metrics['wape_percent']:.2f}% | {metrics['r2']:.4f} |"
            )
    lines.extend(
        [
            "",
            "O benchmark usa somente área privativa e separa bairros entre as cinco partições; "
            "`avaliacao_brl_m2`, preço de venda, desconto, endereço, link, SQL e identificador "
            "não são preditores. É uma validação cruzada espacial interna ao mesmo lote e fonte, "
            "não uma validação independente nem homologação CAIXA.",
        ]
    )
    feature_validation = summary["caixa_appraisal_feature_validation"]
    if feature_validation.get("result") is not None or (
        feature_validation.get("status") == "exploratory_spatial_feature_ablation"
    ):
        lines.extend(
            [
                "",
                f"**Comparação exploratória de atributos:** {feature_validation['rows_with_area_bedrooms_and_parking']} casos completos "
                f"({feature_validation['complete_case_coverage_percent']:.1f}%); MAE da área privativa "
                f"R$ {feature_validation['baseline_area_rate']['mae_brl']:.2f} versus MAE da estratificação "
                f"por área + quartos + vagas R$ {feature_validation['area_bedrooms_parking_groups']['mae_brl']:.2f}. "
                f"MdAPE: {feature_validation['baseline_area_rate']['median_absolute_percentage_error_percent']:.2f}% "
                f"versus {feature_validation['area_bedrooms_parking_groups']['median_absolute_percentage_error_percent']:.2f}%; "
                f"P90 APE: {feature_validation['baseline_area_rate']['p90_absolute_percentage_error_percent']:.2f}% "
                f"versus {feature_validation['area_bedrooms_parking_groups']['p90_absolute_percentage_error_percent']:.2f}%. "
                f"Fallback para a referência de área em {feature_validation['enriched_group_prediction_fallback_rows']} casos. "
                "Resultado exploratório: não comprova qualidade dos atributos, não autoriza seleção do modelo nem treino.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                f"**Comparação de atributos não executada:** {feature_validation['rows_with_area_bedrooms_and_parking']} "
                f"casos completos, abaixo do mínimo exploratório de {feature_validation['minimum_rows_required']}.",
            ]
        )
    temporal_validation = summary["caixa_appraisal_temporal_validation"]
    if temporal_validation["temporal_validation_possible"]:
        temporal_text = (
            f"Holdout cronológico: treino até {temporal_validation['training_end_date']}, "
            f"teste a partir de {temporal_validation['test_start_date']} "
            f"({temporal_validation['test_rows']} linhas), MAE R$ "
            f"{temporal_validation['metrics']['mae_brl']:.2f}."
        )
    else:
        temporal_text = (
            f"Validação temporal bloqueada: {temporal_validation['reason']} "
            f"Data-base disponível em {temporal_validation['dated_candidate_rows']} "
            f"candidatos e {temporal_validation['distinct_appraisal_dates']} datas distintas. "
            "Não usar data de coleta como substituta."
        )
    lines.extend(
        [
            "",
            "## Validação cronológica e atributos adicionais",
            "",
            temporal_text,
            "",
            "| Atributo | Disponibilidade | Classificação | Como obter na operação | Recomendação |",
            "|---|---:|---|---|---|",
        ]
    )
    for attribute in summary["caixa_appraisal_attribute_inventory"]:
        lines.append(
            f"| {attribute['attribute']} | {attribute['available_rows']} | "
            f"{attribute['classification']} | {attribute['operation_path']} | "
            f"{attribute['recommendation']} |"
        )
    lines.extend(
        [
            "",
            "## Simulação e verificação independente dos cálculos",
            "",
            f"A rotina `scripts/validate_caixa_calculations.py` recalcula os indicadores a partir do CSV original e compara com a auditoria persistida. "
            f"Resultado atual: **{summary['caixa_calculation_checks_passed']} verificações aprovadas e "
            f"{summary['caixa_calculation_checks_failed']} falhas**. A simulação aritmética conhecida usa "
            "alvos [100, 200, 300] e previsões [90, 220, 300]: MAE R$ 10, RMSE R$ 12,91, MdAPE 10%, "
            "P90 APE 10%, WAPE 5%, sMAPE 6,6834% e R² 0,975.",
            "",
            "O percentil P90 atual é calculado como estatística de ordem observada no índice "
            "`floor((n-1)*0,9)`, não por interpolação. A verificação confirma a aritmética conforme "
            "essa definição; não constitui validação dos rótulos, da fonte nem do desempenho operacional. "
            "O relatório agregado de execução é `scripts/dados/caixa_sp_validacao_calculation_check.json`.",
            "",
            "## Experimento temporal de transações ITBI",
            "",
            f"Divisão temporal: {summary['itbi_experiment_training_rows'] or 'ND'} registros de treino "
            f"e {summary['itbi_experiment_test_rows'] or 'ND'} de teste, sem SQL presente nos dois conjuntos. "
            "O alvo é exclusivamente o valor declarado pelo contribuinte.",
            "",
            "| Estimador | MAE (R$) | MdAPE | P90 APE | WAPE | R² |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for name, label in (
        ("global_median", "Mediana global"),
        ("pattern_median", "Mediana por padrão IPTU"),
        ("cep_pattern_median", "CEP + padrão IPTU"),
    ):
        estimator = (summary["itbi_experiment_estimators"] or {}).get(name)
        if estimator:
            values = estimator["test_metrics"]
            lines.append(
                f"| {label} | {values['mae_brl']:.2f} | "
                f"{values['median_absolute_percentage_error_percent']:.2f}% | "
                f"{values['p90_absolute_percentage_error_percent']:.2f}% | "
                f"{values['wape_percent']:.2f}% | {values['r2']:.4f} |"
            )
    target_quality = summary["itbi_experiment_target_quality"] or {}
    training_quality = target_quality.get("training", {})
    test_quality = target_quality.get("test", {})
    training_low_value_count = training_quality.get("below_1000_brl_count")
    training_cent_count = training_quality.get("one_cent_value_count")
    low_value_count = test_quality.get("below_1000_brl_count")
    test_cent_count = test_quality.get("one_cent_value_count")
    lines.extend(
        [
            "",
            f"**Ressalva de qualidade:** treino contém {training_low_value_count if training_low_value_count is not None else 'ND'} "
            f"valores abaixo de R$ 1.000 ({training_cent_count if training_cent_count is not None else 'ND'} a R$ 0,01); "
            f"teste contém {low_value_count if low_value_count is not None else 'ND'} "
            f"({test_cent_count if test_cent_count is not None else 'ND'} a R$ 0,01). Esses valores foram mantidos "
            "por falta de critério documentado "
            "para exclusão; por isso, o MAPE bruto é muito sensível e não deve ser interpretado isoladamente. "
            "A revisão desses registros com a fonte é necessária. Nenhuma métrica aqui mede erro de avaliação "
            "de mercado ou libera uso operacional.",
            "",
            "## Regras de separação",
            "",
            "- **Avaliação:** o alvo escolhido para o primeiro modelo; aceitar apenas avaliações de mercado finais, autorizadas, com data-base, método, documento e identidade da unidade verificáveis.",
            "- **ITBI:** valor declarado de transação; manter como referência de transações, nunca como avaliação ou valor fiscal.",
            "- **Experimento ITBI:** comparadores globais e segmentados são avaliados em holdout temporal de transações declaradas. Métricas não representam desempenho em avaliações e não liberam previsão operacional.",
            "- **Oferta:** preço pedido na data de captura; manter dataset/alvo separado, sem desconto uniforme não validado.",
            "- **Fiscal:** valor venal/base de cálculo e campos fiscais não são rótulos de avaliação.",
            "- **Atributos enriquecidos:** célula preenchida não é evidência. Guardar referência, data, entidade (unidade/edifício), classe observada/extraída/calculada/estimada e resultado da validação.",
            "- **Legado:** dataset `dados_sp_ref.csv` e modelos antigos permanecem em quarentena; não usar para treino ou métricas. Os artefatos `.pkl`, metadados e gráficos ficam em `arquivo_legado/models/`.",
            "",
            "## Rotina de atualização",
            "",
            "Na raiz do projeto, executar `python -B scripts\\\\train_itbi_experiment.py` para regenerar o experimento de transações ITBI e `python -B scripts\\\\build_data_catalog.py` para atualizar o catálogo. O treino não altera os dados originais nem libera o modelo de avaliação.",
            "",
            "O relatório completo, hashes SHA-256, tamanhos, contagens e resultados dos auditores ficam em `dados/derivados/catalogo_bases.json`.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN)
    args = parser.parse_args()
    catalog = build_catalog()
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(render_markdown(catalog), encoding="utf-8")
    print(
        f"Catálogo gerado: {args.json_output}; "
        f"avaliações={catalog['summary']['appraisal_label_rows']}; "
        f"ofertas={catalog['summary']['offer_rows']}; "
        "treinamento_liberado=False"
    )
    return 0 if not catalog["summary"]["missing_catalog_sources"] else 1


if __name__ == "__main__":
    sys.exit(main())
