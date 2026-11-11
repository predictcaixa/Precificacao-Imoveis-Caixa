# Catálogo e organização das bases

**Gerado em UTC:** 2026-10-27T00:56:30.930302+00:00

> O catálogo organiza os arquivos sem mover ou alterar as fontes originais. A classificação documenta uso e limitações; não representa aprovação de dados nem liberação de treinamento.

## Resumo atual

| Indicador | Resultado |
|---|---:|
| Avaliações de mercado no template | 0 |
| Avaliações candidatas à revisão técnica | 0 |
| Lote CAIXA: linhas / candidatas à validação espacial | 480 / 478 |
| Cobertura da data de avaliação CAIXA | 0.0% |
| Validação temporal CAIXA | blocked_missing_appraisal_date |
| Verificação independente dos cálculos | 100 aprovados / 0 falhas |
| Anúncios no template auditado | 0 |
| Transações ITBI elegíveis | 42826 |
| Experimento ITBI: treino / teste | 31222 / 11394 |
| Ligações enriquecidas únicas | 9658 |
| Ligações enriquecidas ambíguas | 2 |
| Treinamento liberado | Não |

## Bases classificadas

| Base | Arquivo | Natureza/alvo | Registros | Uso permitido agora | Elegibilidade para treino |
|---|---|---|---:|---|---|
| Transações declaradas ITBI/PMSP | `dados/1. APARTAMENTOS.xlsx` | transaction / Valor declarado pelo contribuinte em transação ITBI | 45103 | referência experimental de transações e análise técnica | not_a_CAIXA_appraisal_target |
| Planilha enriquecida de imóveis | `dados/22.10.2026.xlsx` | mixed_unverified_attributes / sem alvo | 9660 | auditoria de vínculo e investigação de proveniência | not_training_eligible_without_attribute_evidence |
| Rótulos de avaliações de mercado | `dados/derivados/avaliacoes_imoveis_template.csv` | appraisal / valor de mercado avaliado em R$ na data-base da avaliação | 0 | entrada controlada para auditoria de avaliações autorizadas | blocked_until_expert_review_and_independent_validation |
| Lote CAIXA de avaliações para validação | `scripts/dados/caixa_sp_validacao.csv` | caixa_appraisal_validation_candidate / Valor de avaliação CAIXA de imóvel retomado | 480 | auditoria de rótulos e benchmark espacial exploratório | candidate_labels_pending_expert_review |
| Verificação independente dos cálculos CAIXA | `scripts/dados/caixa_sp_validacao_calculation_check.json` | calculation_verification / sem alvo | 100 | verificação reprodutível da aritmética e das métricas reportadas | not_training_data |
| Ofertas imobiliárias | `dados/derivados/ofertas_imoveis_template.csv` | asking_price_offer / preço pedido no anúncio na data/hora da captura | 0 | auditoria de uma base de oferta separada, após confirmar direitos de uso | separate_target_not_appraisal |
| Dataset provisório de auditoria e integração | `dados/derivados/avm_dataset_provisorio.csv` | audit_join / nenhum rótulo de avaliação preenchido | 9660 | rastreabilidade, conferência e revisão de atributos | blocked |
| Perfil do comparador experimental ITBI | `models/itbi_reference_2026.json` | derived_transaction_reference / transação declarada ITBI | 42826 | referência exploratória e backtest temporal ITBI | not_an_appraisal_model |
| Experimento de modelo para transações ITBI | `models/itbi_transaction_experiment.json` | experimental_declared_transaction_model / Valor declarado pelo contribuinte em transação ITBI | ND | benchmark técnico experimental contra transações ITBI | not_a_CAIXA_appraisal_model_or_operational_predictor |
| Dados legados derivados | `dados/dados_sp_ref.csv` | legacy_derived / preço legado sem proveniência adequada | 12151 | quarentena e referência de auditoria histórica apenas | prohibited |
| Referência técnica IUP/IBAPE | `dados/Padrão Construtivo - FOTOS e características das Edificações - IBAPE SP .pdf` | technical_reference / sem alvo | ND | consulta metodológica dentro do escopo documentado | not_a_data_source |

## Lote CAIXA de avaliações — validação exploratória

O arquivo `scripts/dados/caixa_sp_validacao.csv` contém 480 linhas; 478 atendem aos filtros estruturais iniciais para benchmark espacial (apartamento, área privativa e alvo positivo). A cobertura de `avaliacao_data` é 0.0%. A validação temporal está `blocked_missing_appraisal_date`; todos os rótulos continuam candidatos a revisão, sem liberação para treino ou operação.

| Estimador-base | MAE (R$) | MdAPE | P90 APE | WAPE | R² |
|---|---:|---:|---:|---:|---:|
| Mediana municipal do valor de avaliação no conjunto de treino. | 90699.93 | 12.96% | 39.94% | 30.60% | -0.0512 |
| Mediana de avaliação por m² no treino multiplicada pela área privativa. | 65791.72 | 14.76% | 39.66% | 22.20% | 0.7020 |

O benchmark usa somente área privativa e separa bairros entre as cinco partições; `avaliacao_brl_m2`, preço de venda, desconto, endereço, link, SQL e identificador não são preditores. É uma validação cruzada espacial interna ao mesmo lote e fonte, não uma validação independente nem homologação CAIXA.

**Comparação exploratória de atributos:** 92 casos completos (19.2%); MAE da área privativa R$ 116770.56 versus MAE da estratificação por área + quartos + vagas R$ 113304.77. MdAPE: 18.80% versus 16.91%; P90 APE: 39.28% versus 41.56%. Fallback para a referência de área em 24 casos. Resultado exploratório: não comprova qualidade dos atributos, não autoriza seleção do modelo nem treino.

## Validação cronológica e atributos adicionais

Validação temporal bloqueada: A data-base da avaliação é necessária; data_coleta não a substitui. Data-base disponível em 0 candidatos e 0 datas distintas. Não usar data de coleta como substituta.

| Atributo | Disponibilidade | Classificação | Como obter na operação | Recomendação |
|---|---:|---|---|---|
| area_ref_m2 | 478 | extraido_sem_documentacao_independente | Matrícula/documento da unidade ou campo validado na solicitação CAIXA. | Usar somente após confirmar definição, unidade e vínculo com a unidade. |
| quartos | 406 | extraido_com_evidencia_da_unidade_pendente | Documento/planta/anúncio da mesma unidade, com vínculo e evidência arquivados. | Não completar por equivalência com área; manter ausente se não comprovado. |
| vagas | 107 | extraido_com_evidencia_da_unidade_pendente | Matrícula/documento da vaga ou campo validado na solicitação CAIXA. | Não tratar vaga do edifício como vaga privativa da unidade. |
| banheiros | 0 | ausente | Documento/planta da unidade, se disponível no fluxo CAIXA. | Solicitar dado ou manter ausente; não estimar sem amostra de validação independente. |
| elevador | 0 | ausente | Documento ou cadastro do edifício identificado por torre/bloco. | Não inferir por anúncio de outra unidade sem provar mesmo edifício/bloco. |
| idade_construcao | 0 | ausente | Ano de construção de fonte/documento válido e data-base recebida na operação. | Calcular apenas com fonte do ano e data-base documentadas. |
| conservacao_condominio | 0 | ausente | Inspeção ou evidência atual do edifício, caso requisito seja confirmado. | Não inferir por idade, preço ou imagem isolada. |
| avaliacao_data | 0 | ausente_no_lote_atual | Laudo/documento da avaliação CAIXA. | Obrigatória para validação temporal; data de coleta não substitui. |

## Simulação e verificação independente dos cálculos

A rotina `scripts/validate_caixa_calculations.py` recalcula os indicadores a partir do CSV original e compara com a auditoria persistida. Resultado atual: **100 verificações aprovadas e 0 falhas**. A simulação aritmética conhecida usa alvos [100, 200, 300] e previsões [90, 220, 300]: MAE R$ 10, RMSE R$ 12,91, MdAPE 10%, P90 APE 10%, WAPE 5%, sMAPE 6,6834% e R² 0,975.

O percentil P90 atual é calculado como estatística de ordem observada no índice `floor((n-1)*0,9)`, não por interpolação. A verificação confirma a aritmética conforme essa definição; não constitui validação dos rótulos, da fonte nem do desempenho operacional. O relatório agregado de execução é `scripts/dados/caixa_sp_validacao_calculation_check.json`.

## Experimento temporal de transações ITBI

Divisão temporal: 31222 registros de treino e 11394 de teste, sem SQL presente nos dois conjuntos. O alvo é exclusivamente o valor declarado pelo contribuinte.

| Estimador | MAE (R$) | MdAPE | P90 APE | WAPE | R² |
|---|---:|---:|---:|---:|---:|
| Mediana global | 291235.72 | 29.09% | 78.33% | 39.76% | 0.4204 |
| Mediana por padrão IPTU | 269748.75 | 27.21% | 74.12% | 36.83% | 0.5452 |
| CEP + padrão IPTU | 254020.79 | 23.63% | 70.58% | 34.68% | 0.5533 |

**Ressalva de qualidade:** treino contém 105 valores abaixo de R$ 1.000 (60 a R$ 0,01); teste contém 32 (15 a R$ 0,01). Esses valores foram mantidos por falta de critério documentado para exclusão; por isso, o MAPE bruto é muito sensível e não deve ser interpretado isoladamente. A revisão desses registros com a fonte é necessária. Nenhuma métrica aqui mede erro de avaliação de mercado ou libera uso operacional.

## Regras de separação

- **Avaliação:** o alvo escolhido para o primeiro modelo; aceitar apenas avaliações de mercado finais, autorizadas, com data-base, método, documento e identidade da unidade verificáveis.
- **ITBI:** valor declarado de transação; manter como referência de transações, nunca como avaliação ou valor fiscal.
- **Experimento ITBI:** comparadores globais e segmentados são avaliados em holdout temporal de transações declaradas. Métricas não representam desempenho em avaliações e não liberam previsão operacional.
- **Oferta:** preço pedido na data de captura; manter dataset/alvo separado, sem desconto uniforme não validado.
- **Fiscal:** valor venal/base de cálculo e campos fiscais não são rótulos de avaliação.
- **Atributos enriquecidos:** célula preenchida não é evidência. Guardar referência, data, entidade (unidade/edifício), classe observada/extraída/calculada/estimada e resultado da validação.
- **Legado:** dataset `dados_sp_ref.csv` e modelos antigos permanecem em quarentena; não usar para treino ou métricas.
- Os artefatos do treinamento legado (`.pkl`, metadados e gráficos) foram movidos para `arquivo_legado/models/`; consulte `arquivo_legado/README.md`. O AVM atual mantém seus modelos em `models/offer_avm/`.

## Rotina de atualização

Na raiz do projeto, executar `python -B scripts\\train_itbi_experiment.py` para regenerar o experimento de transações ITBI e `python -B scripts\\build_data_catalog.py` para atualizar o catálogo. O treino não altera os dados originais nem libera o modelo de avaliação.

O relatório completo, hashes SHA-256, tamanhos, contagens e resultados dos auditores ficam em `dados/derivados/catalogo_bases.json`.
