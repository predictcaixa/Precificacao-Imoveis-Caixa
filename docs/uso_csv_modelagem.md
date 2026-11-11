# CSV provisório para análise e preparação do AVM

## O que os PDFs definem sobre o alvo

O relatório de precificação da CAIXA é um formulário de análise e governança. Na seção de origem/composição da base, os itens “oferta”, “transação”, “avaliação” e “registro” aparecem como alternativas sem seleção. O documento solicita que a natureza e o período dos dados sejam informados, mas não escolhe qual valor deve ser previsto. O utilizador definiu depois que o alvo desejado é valor de avaliação.

O relatório também distingue variáveis do imóvel e valor de mercado na análise exploratória, e pede descrição dos dados usados como entrada e dos resultados fornecidos pelo modelo. Isso não determina a origem do campo `Valor Total.` da planilha enriquecida.

O PDF de respostas objetivas sobre IUP/IBAPE recomenda distinguir transações realizadas de ofertas e afirma que a CAIXA deve definir formalmente as fontes autorizadas. A saída mínima sugerida é valor estimado, valor unitário e memória/rastreabilidade; esse requisito de saída não equivale a definir a variável-alvo de treinamento.

**Conclusão:** o tipo desejado é avaliação, mas os PDFs não identificam uma coluna de avaliações na planilha. A fonte do valor-alvo continua por localizar e deve ser confirmada no protocolo CAIXA.

## Arquivos gerados

- `dados/derivados/avm_dataset_provisorio.csv`: 9.660 linhas, uma por registro da planilha enriquecida, ligadas à fonte municipal por SQL + data + valor declarado. Preserva 9.658 vínculos únicos e 2 ambíguos; não descarta silenciosamente nenhum registro.
- `dados/derivados/avm_dicionario_provisorio.csv`: definição, unidade, fonte, escopo, classificação, cobertura, status de validação e recomendação para cada coluna.

Os CSVs são UTF-8 com BOM para facilitar abertura em ferramentas comuns. O identificador SQL é incluído apenas para rastreabilidade/agrupamento; não é feature recomendada. Endereço completo e matrícula não são copiados para o CSV.

## Como interpretar com segurança

- `selected_target_type` está definido como `avaliacao`; `selected_target_value_brl` continua vazio porque não foram encontrados rótulos de avaliação; `model_training_eligible` é `false` em todas as linhas.
- `itbi_declared_transaction_brl` é o valor declarado pelo contribuinte na fonte municipal e permanece separado dos valores fiscais.
- `candidate_total_value_brl` coincide exatamente com `tax_base_value_brl` em todos os 9.658 vínculos únicos; deve ser interpretado como base fiscal do ITBI, não avaliação.
- `candidate_unit_value_brl` é derivado do total dividido pela área privativa e não é um alvo independente nem deve ser feature de preço.
- `*_raw_unverified` conserva valores da planilha enriquecida para investigação, mas não recomenda seu uso como feature.
- `unit_attribute_evidence_status` e `building_attribute_evidence_status` marcam atributos sem evidência validada da unidade/edifício.
- Registros ambíguos não recebem campos municipais de vínculo único. Devem ser resolvidos por evidência adicional ou excluídos de treino, com exclusão documentada.

O campo `candidate_unit_value_brl` coincide com `candidate_total_value_brl / private_area_m2_raw_unverified` nos dados auditados. Não o use como preditor se o valor total vier a ser escolhido como alvo: há risco de vazamento/circularidade.

## Reproduzir a exportação

Na raiz do projeto:

```powershell
python -B scripts\build_modeling_csv.py
python -B -m unittest test_modeling_csv
```

Os caminhos podem ser alterados com `--dataset-output` e `--dictionary-output`. O script lê as planilhas originais sem modificá-las e não acessa serviços externos.

## Antes de treinar

1. Solicitar à CAIXA avaliações finais autorizadas/anônimas, com valor, data-base, finalidade, método, tipologia, identificador da unidade e status de revisão.
2. Excluir `Valor Total.` como alvo de avaliação: a correspondência local indica base fiscal ITBI; excluir também `Valor Unit.` para evitar circularidade/vazamento.
3. Confirmar definição, unidade e proveniência das áreas; validar quartos, banheiros, vagas por evidência da própria unidade e elevador no nível do edifício.
4. Confirmar quais atributos estarão disponíveis no momento da operação CAIXA e registrar as fontes públicas/documentais no mapa de origens.
5. Criar um conjunto de treino derivado, elegível e versionado, sem colunas fiscais usadas como rótulo, ambiguidades ou vazamento.

Este CSV permite trabalhar em arquivos simples, sem banco de dados, mas ainda é um artefato de auditoria/integração e não um conjunto aprovado para treinar ou emitir preços.

## Trilha preparada para o alvo escolhido: valor de avaliação

O utilizador escolheu valor de avaliação como alvo do primeiro modelo. Para tratar esse bloqueio sem usar ITBI ou oferta como rótulo substituto, foi criado:

- `dados/derivados/avaliacoes_imoveis_template.csv`: contrato de dados para avaliações finais de valor de mercado, com referência à unidade, data-base, método, documento/evidência, permissão de uso e proveniência da área.
- `scripts/audit_evaluation_csv.py`: auditoria sintática do CSV e de evidências declaradas. Identifica linhas candidatas à revisão técnica, duplicidades, campos ausentes e cobertura documental dos atributos. Não lê nem envia documentos, não confirma autenticidade, não calcula representatividade e **nunca habilita treinamento**.
- Endpoint `GET /avaliacao/auditoria` e campo `auditoria_avaliacoes` em `GET /modelo/info`: disponibilizam o resultado da triagem para a interface.

Executar na raiz do projeto:

```powershell
python -B scripts\audit_evaluation_csv.py
python -B -m unittest test_evaluation_csv
```

Preencher somente com avaliações reais autorizadas. Usar token pseudonimizado da unidade, não CPF, nome, endereço completo ou matrícula no CSV. Guardar documentos somente em repositório/ambiente autorizado; inserir no arquivo referências internas e hash SHA-256 do documento, nunca o conteúdo confidencial. `source_permission` deve refletir autorização/legalidade confirmada, não uma suposição.

Uma linha passar na triagem significa apenas que os campos mínimos foram fornecidos de forma consistente. Ainda é necessária revisão por profissional habilitado, validação de amostra, análise de cobertura/representatividade, separação treino/validação/teste por unidade e tempo, compatibilidade com dados da OS, seleção de variáveis, avaliação de métricas e aprovação do método. Repetições da mesma unidade devem permanecer no mesmo grupo de validação para evitar vazamento. Não há limiar universal de amostra codificado.

O template está vazio enquanto não forem fornecidas avaliações de valor de mercado identificadas e autorizadas. Portanto, o bloqueio de treinamento é real e permanece ativo; a infraestrutura empresarial e a ferramenta de IA para leitura de matrículas também dependem de evidência e recursos da empresa.
