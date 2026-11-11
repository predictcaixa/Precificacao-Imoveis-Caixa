# Relatório do Modelo de Precificação — Rascunho de trabalho

**Edital:** CAIXA nº 012/2026  
**Localidade do formulário:** São Paulo/SP  
**Tipologia:** Apartamentos  
**Situação deste arquivo:** rascunho interno incompleto; não assinar, converter em declaração final nem enviar à CAIXA sem validação dos responsáveis.

> O PDF da CAIXA diz que a apresentação do Relatório do Modelo não constitui homologação nem autorização para início do fluxo. Também exige que o documento represente fielmente o modelo apresentado, seja assinado pelos responsáveis e enviado em PDF/A. O prazo indicado no PDF fornecido é 30/10/2026. Este rascunho organiza evidências, mas não substitui o formulário oficial.

## Legenda de preenchimento

- **[EVIDÊNCIA LOCAL]** confirmado em arquivos/código do projeto.
- **[DECISÃO DA PRECIFICADORA]** escolha técnica ainda deve ser feita e aprovada pelos responsáveis.
- **[EVIDÊNCIA DA EMPRESA]** precisa de informação ou documento da empresa; não pode ser inferido do repositório.
- **[CONFIRMAR OFICIALMENTE]** depende de conferir edital, retificação ou esclarecimento formal; mensagens de WhatsApp não bastam.
- **[NÃO APLICÁVEL — JUSTIFICAR]** preencher somente se a não aplicabilidade estiver tecnicamente justificada.

Não substituir pendências por estimativas, textos genéricos ou declarações de infraestrutura/segurança que não tenham evidência.

## Decisão de escopo que precisa preceder a versão assinada

O Relatório do Modelo solicita que a natureza dos dados seja identificada (oferta, transação, avaliação, registro ou outra), mas não escolhe uma por conta da empresa. As respostas encaminhadas por WhatsApp atribuem à precificadora a definição metodológica e dizem que preços de oferta podem ser usados como variável resposta se o método for documentado e fundamentado. Isso **não** torna preço ofertado equivalente a transação ou avaliação.

Escolher e usar apenas uma definição por versão de modelo:

| Opção de escopo | Rótulo que pode ser declarado | Evidência atualmente no repositório | Pode ser descrito como avaliação CAIXA? |
|---|---|---|---|
| Comparador ITBI atual | Valor declarado de transação de compra e venda registrado no ITBI, em 2026 | 42.826 transações elegíveis, filtro e backtest temporal documentados | **Não.** É apenas referência comparativa de transações; não foi calibrado contra avaliações. |
| Modelo de ofertas | Preço pedido no anúncio na data/hora de captura | CSV template sem observações; auditoria encontrou 0 anúncios | **Não automaticamente.** A saída é preço pedido anunciado. Qualquer uso como proxy de avaliação requer fundamentação e validação independente apropriadas. |
| Modelo de avaliação | Valor de avaliação, com data-base, finalidade, método e unidade definidos | Nenhum rótulo de avaliação rastreável identificado. `Valor Total.` coincide com base fiscal ITBI nos 9.658 vínculos únicos. | Somente após construir e validar metodologia coerente com esse alvo e documentar as limitações. |

**Opção selecionada para este relatório:** [DECISÃO DA PRECIFICADORA — preencher]  
**Justificativa do alvo e compatibilidade com o objeto do edital:** [DECISÃO DA PRECIFICADORA — preencher]  
**Se for mantido o comparador ITBI:** intitular e apresentar como referência experimental de transações, sem declarar avaliação.  
**Se for escolhido preço de oferta:** descrever preço pedido e data de captura como alvo próprio, sem aplicar desconto uniforme não validado.  
**Se for declarado valor de avaliação:** não usar o alvo ITBI/oferta como se fosse avaliação; documentar como o valor de avaliação é produzido e validado.

## 1. Informações gerais

| Campo | Preenchimento do rascunho |
|---|---|
| Razão social | [EVIDÊNCIA DA EMPRESA — preencher conforme contrato] |
| CNPJ | [EVIDÊNCIA DA EMPRESA — preencher] |
| Nº do contrato de credenciamento CAIXA | [EVIDÊNCIA DA EMPRESA — preencher] |
| Cidades/regiões metropolitanas | São Paulo/SP, se esta for a localidade efetivamente selecionada |
| Tipologia | Apartamentos |
| Nome do modelo | [DECISÃO DA PRECIFICADORA — nome e alvo explícito] |
| Versão vigente | [DECISÃO DA PRECIFICADORA — versionar código, dados, parâmetros e artefato] |
| Data de elaboração / início e fim de vigência | [EVIDÊNCIA DA EMPRESA — preencher; não retroagir] |
| Responsável técnico pelo modelo | [EVIDÊNCIA DA EMPRESA — nome, CPF, formação, titulação, vínculo e assinatura] |
| Responsável pela análise do mercado | [EVIDÊNCIA DA EMPRESA — nome, CPF, formação, titulação em avaliações, CREA/CAU, vínculo e assinatura] |
| Responsável por inserir dados e emitir relatório | [EVIDÊNCIA DA EMPRESA — nome, CPF, formação, CREA/CAU, vínculo e assinatura] |
| Responsável legal | [EVIDÊNCIA DA EMPRESA — nome, CPF, cargo e assinatura] |

### 1.1 Controle de versão e vigência

| Item | Informação |
|---|---|
| Quantidade bruta de registros | Para a fonte municipal `1. APARTAMENTOS.xlsx`, aba `2026`: 45.103 linhas de dados. Para a planilha enriquecida `22.10.2026.xlsx`: 9.660 registros. Não somar bases de naturezas diferentes como se fossem uma amostra única. |
| Quantidade após saneamento | Para o comparador ITBI: 42.826 transações elegíveis únicas; filtros e exclusões descritos em `models/itbi_reference_2026.json`. Para um modelo de oferta/avaliação: não há conjunto de treino elegível identificado. |
| Período | Fonte ITBI do comparador: 02/01/2026 a 07/09/2026. |
| Atualização pretendida | [DECISÃO DA PRECIFICADORA — propor ciclo, justificar e demonstrar capacidade; resposta compartilhada informa possível redução para 6 meses.] |
| Evidência de mudança/versionamento | [EVIDÊNCIA DA EMPRESA — hash da base, commit/versão de código, ambiente/dependências, parâmetros, artefato, relatório e data.] |

### 1.2–1.5 Responsáveis

Preencher integralmente as qualificações, vínculos, atribuições e assinaturas digitais no formulário oficial. **Não deixar em branco** e não inventar nomes ou registros profissionais.

## 2. Descrição e análise exploratória

### 2.1 Origem e composição da base

| Campo do formulário | Situação/evidência |
|---|---|
| Fontes autorizadas | ITBI/PMSP é fonte municipal usada pelo comparador, sujeita aos termos de publicação aplicáveis. Para ofertas, nenhuma fonte foi coletada/auditada ainda; a coleta própria exige revisão legal e documental por portal. [Anexar base legal/licença/termos e autorização de uso quando aplicável.] |
| Natureza dos dados | Para o comparador existente: **transação declarada ITBI**. A base contém também campos fiscais distintos. Não assinalar oferta ou avaliação para esse comparador. |
| Período de coleta/observação | 02/01/2026–07/09/2026 para transações ITBI elegíveis. |
| Periodicidade de atualização | [DECISÃO DA PRECIFICADORA — propor e justificar; indicar plano para atualização semestral caso solicitado.] |
| Cobertura territorial | Município de São Paulo/SP no conjunto municipal ITBI; não representa carteira CAIXA nem outros municípios. |
| Tipologia | Uso IPTU 20 e código de padrão 20–25, conforme filtros do script; códigos não foram validados como padrão IBAPE. |
| Unidade de área | Área Construída (m²) do cadastro IPTU, exclusivamente no comparador atual. Não equivale automaticamente à área privativa, à área total ou à área fiscal definida por outro campo. |
| Unidade monetária | R$ correntes conforme registro de transação; o comparador não fez atualização monetária da amostra. |
| Representatividade | Não comprovada para carteira CAIXA. Quantidade de linhas não prova cobertura representativa. Incluir distribuição por período, região, faixa de área/valor, padrão, suporte local e segmentos sem suporte, calculada para o alvo final. |

**Fontes locais identificadas:**  
1. `dados/1. APARTAMENTOS.xlsx`, aba `2026`: dados cadastrais, valores declarados e fiscais, data/natureza, área construída IPTU e localização.  
2. `dados/22.10.2026.xlsx`, aba `9662 DADOS`: planilha enriquecida cuja linhagem de atributos internos não foi comprovada.  
3. CSVs derivados em `dados/derivados/`: artefatos de auditoria, não dados novos independentes.

**Associação entre fontes:** SQL + data da transação + valor declarado: 9.660/9.660 registros encontram correspondência; 9.658 únicas e 2 ambíguas. As ambíguas não são resolvidas silenciosamente.

### 2.2–2.4 Variáveis e campos operacionais

O PDF lista campos que devem constar no Relatório de Precificação por imóvel e uma tabela de variáveis do modelo. Não confundir esses campos de saída/operação com features efetivamente disponíveis na base de desenvolvimento.

| Campo/variável | Definição operacional e unidade | Disponível nos dados atuais? | Tratamento no rascunho |
|---|---|---|---|
| Matrícula, cartório, endereço e CEP | Identificação documental e geográfica do imóvel | Matrícula/endereço existem na planilha enriquecida; CEP municipal disponível. O esclarecimento encaminhado diz que matrícula, código do imóvel, OS e endereço podem vir na OS, mas não foi testada uma OS real. | Verificar coerência e origem por caso; não presumir que matrícula contenha todos os atributos. Proteger dados pessoais/documentos. |
| Data e valor da precificação | Data-base e valor produzido pelo modelo | Não há valor operacional de avaliação gerado pelo comparador | Só preencher em Relatório de Precificação por imóvel quando o fluxo estiver autorizado; distinguir de teste exploratório. |
| Tipo e implantação | Apartamento; condomínio conforme escopo do formulário | Tipologia selecionada no recorte; demais campos devem ser conferidos por caso | Não extrapolar para tipologia sem validação. |
| Área total | m² segundo definição oficial do atributo | Coluna `Área total` preenchida na planilha enriquecida, mas sem dicionário/proveniência confirmados | Não usar até definição e reconciliação documental. |
| Área de uso privativo | m² formalmente cadastrado para a unidade | Campo preenchido na planilha enriquecida, mas sem evidência documental por unidade | Recomendação recebida: priorizar área privativa formalmente cadastrada. Verificar documento e tratar divergências; jardins/quintais/terraços exclusivos em campos separados até validação. |
| Dormitórios | Contagem por unidade | Coluna enriquecida preenchida; origem/evidência da unidade não verificada; ausente no ITBI | Não inferir pela área. Buscar em documento da própria unidade e registrar evidência. |
| Vagas privativas | Contagem de vagas vinculadas à unidade | Coluna enriquecida preenchida; origem/vínculo não verificados; ausente no ITBI | Confirmar matrícula/convenção/documento da unidade; não usar vagas do condomínio como se fossem da unidade. |
| Banheiros | Contagem por unidade; definição de lavabo/serviço deve ser registrada | Coluna enriquecida preenchida, origem não verificada; ausente no ITBI | Variável adicional segundo o formulário; obter evidência própria e definir contagem. |
| Elevador | Existência/atributo do edifício | Coluna enriquecida 0/1, fonte/data não verificadas; ausente no ITBI | Associar ao edifício identificado, com evidência e data. |
| Estado de conservação do condomínio | Conforme escala da versão vigente do formulário | Não identificado nas bases. Mensagem encaminhada diz que foi excluído do item 2.2.1 | [CONFIRMAR OFICIALMENTE] retificação antes de preencher. Não tratar como obrigatório enquanto versão oficial não for conferida; se adicional, justificar e validar. |
| Idade/ano de produção | Idade ou ano conforme definição do formulário, unidade/anos | `IDADE` existe na planilha enriquecida e corresponde a `2026 - ACC (IPTU)`; divergências de ACC em 51 dos vínculos únicos | Classe calculada, não idade observada; validar fonte/data-base e não equiparar a conservação nem à idade estimada IBAPE. |
| Localização derivada | CEP, geocódigo ou variáveis espaciais documentadas | Coordenadas e setor preenchidos na planilha, mas linhagem/precisão não validadas | Não usar como feature até validar método, datum, precisão, geocodificação e compatibilidade operacional. |
| Conservação da unidade | Condição interna, não sinônimo da conservação do condomínio | Ausente | Não inferir por idade/anúncio/foto isolada. Só incluir após método/evidência autorizados e validação. |

**2.3 Variáveis adicionais CAIXA:** transcrever a versão oficial vigente do formulário (ex.: idade de produção, banheiros e elevador, conforme PDF local). A conservação do condomínio está listada no PDF local, mas há mensagem de retificação a confirmar.  
**2.4 Variáveis complementares propostas:** [DECISÃO DA PRECIFICADORA — para cada uma, explicar definição, unidade, fonte, cobertura, evidência, associação e benefício demonstrado. Não incluir variáveis apenas por estarem preenchidas.]

### 2.5 Atualização temporal dos valores

Para o comparador ITBI atual: valores não atualizados; o método calcula distribuição de transações no período observado e não converte para valor de outra data-base.

Se atualizar valores no modelo final, preencher objetivo, índice/fonte, data-base, periodicidade, abrangência, fórmula, exceções, justificativa e efeito. Caso não atualize, justificar tecnicamente a compatibilidade da janela temporal com o alvo e medir sensibilidade temporal.

### 2.6 Variável de localização

Para o comparador: CEP e código de padrão IPTU são opcionais para segmentação; quando o suporte local é inferior a 30, há fallback para grupo mais amplo ou município. A regra de 30 é uma regra experimental, não garantia de comparabilidade.

Para o modelo final, documentar:

- Fonte de dados geográficos, método de geocodificação e licença/termos.
- Datum e sistema de coordenadas, se utilizados.
- Uso de latitude/longitude ou alternativa de representação.
- Variáveis espaciais derivadas e método de cálculo.
- Padronização de endereço, controle de precisão e validação amostral.
- Tratamento de divisas, registros sem localização válida e geocodificação incerta.
- Justificativa, cobertura, impacto esperado e compatibilidade com entradas da OS.

Estado atual do projeto: coordenadas na planilha enriquecida existem, mas não há prova suficiente da linhagem/precisão; não declarar geocodificação validada.

### 2.7 Saneamento e qualidade dos dados

| Controle exigido | Evidência e tratamento conhecido |
|---|---|
| Duplicidade/associação | 9.658 correspondências únicas e 2 ambiguidades na junção enriquecida–ITBI; chaves ambíguas não recebem ligação única. Comparador exclui 46 linhas ambíguas na base elegível. |
| Valores ausentes | Dataset de avaliação: 0% de rótulos de avaliação identificados; treinamento bloqueado. Oferta: 0 registros coletados. Campos preenchidos sem proveniência não são tratados como observados válidos. |
| Inconsistência de áreas | Área construída IPTU permanece separada. `Área total` e `Área privativa` não têm definições verificadas; 89 casos com área privativa > área total na auditoria. Não corrigir por regra automática. |
| Divergências cadastrais | ACC (IPTU): 51 divergências; padrão IPTU: 25 divergências entre fontes nos 9.658 vínculos únicos; manter e investigar sem sobrescrever. |
| Outliers/incompatibilidades | O comparador restringe área a 15–1.000 m² e preço/área válidos; isto é filtro de domínio experimental, não política aprovada de outliers para o modelo final. |
| Contemporaneidade | ITBI do comparador: 02/01–07/09/2026. Não há atualização monetária. |
| Vazamento (leakage) | `Valor Total.` coincide com base fiscal; `Valor Unit.` deriva do total/área e ambos são excluídos de um alvo de avaliação. SQL, identificadores e atributos futuros não devem ser features. |
| Rastreabilidade | Scripts reprodutíveis, linhas de origem e relatório de ligação existem. Evidência de proveniência por unidade dos atributos enriquecidos não existe. |
| Validação profissional | [EVIDÊNCIA DA EMPRESA — responsável de análise de mercado deve documentar revisão, casos amostrados, decisões e assinatura.] |

Incluir para cada etapa a contagem e percentual de registros aceitos/excluídos e motivo no relatório final. Anexar `docs/resultado_auditoria_vinculos.json` e relatório de auditoria do dataset final.

### 2.8 Estatísticas descritivas do treinamento

**Não preencher com estatísticas de avaliação:** não há amostra de treinamento de avaliações.  
**Para o comparador ITBI:** gerar tabela de N, média, DP, P1, P25, mediana, P75, P99, mínimo e máximo pelo script versionado para, no mínimo, alvo/preço unitário, área, datas, localização e variáveis utilizadas. Registrar que o conjunto é de transações, não avaliações.  
**Para modelo de oferta:** não calculável enquanto o template permanecer vazio.

### 2.9 Engenharia de atributos

Para o comparador atual, documentar como feature a área construída IPTU e como segmentadores opcionais o CEP e código padrão IPTU; taxa unitária = valor declarado / área construída; resumo robusto por grupo = mediana e percentis; saída = taxa mediana × área confirmada. Não há dormitórios, banheiros, vagas, elevador ou conservação inferidos.

No relatório final incluir lista de variáveis iniciais/criadas/excluídas, fórmulas, encoding, normalização, seleção, multicolinearidade e validação. Se não se aplicarem por ser regra determinística, indicar “não aplicável” e explicar.

### 2.10 Divisão treino/validação/teste

Backtest existente do comparador ITBI: treino janeiro–junho/2026 (31.222); teste julho–07/setembro/2026 (11.394), excluindo do teste registros cujo SQL aparece no treino. Dos 42.826 registros elegíveis, 210 não entram em nenhum dos dois subconjuntos por essa regra de exclusão de SQL repetido; manter esse denominador explicitado e reconciliado no relatório final. No teste, 3.050 registros usaram perfil CEP + padrão IPTU e 8.344 perfil municipal por padrão IPTU. Isto é avaliação temporal retrospectiva na mesma fonte, não teste independente de avaliações CAIXA.

Para o modelo final, descrever amostras, proporções, critérios temporal/geográfico e agrupamento por imóvel/edifício, validação cruzada quando aplicada, média/desvio padrão das métricas e controles contra leakage. Não alegar treino/teste para o modelo de avaliação, pois esse conjunto não foi identificado.

### 2.11 Métricas observadas

**Comparador ITBI somente — não transferir para modelo de avaliação:**

| Métrica | Valor observado | Base |
|---|---:|---|
| MAE | R$ 254.020,79 | Teste temporal de transações ITBI |
| MdAPE | 23,6348% | Teste temporal de transações ITBI |
| P90 do erro percentual absoluto | 70,5847% | Teste temporal de transações ITBI; métrica complementar |
| R² | 0,553255 | Teste temporal de transações ITBI |
| Cobertura da faixa observada P10–P90 | 80,4283% | Não é intervalo de confiança individual |
| Teste | 11.394 transações | Jan–jun treino; jul–07/set teste; sem reuso de SQL entre treino e teste |

MAPE, WAPE, MWAPE e RMSE para o modelo final: [CALCULAR a partir dos resíduos e registrar fórmula/população; não estimar ou transcrever métricas de modelos legados.]  
Os indicadores acima têm erros altos e não demonstram precisão adequada para avaliação/garantia. Não há valores de avaliação observados para cálculo de métricas do alvo de avaliação.

## 3. Metodologias, recursos tecnológicos, estrutura e segurança

### 3.1 Bibliotecas e componentes

| Biblioteca/componente | Versão | Licença | Finalidade | Situação |
|---|---|---|---|---|
| Python | [EVIDÊNCIA DA EMPRESA — registrar versão usada no treino e produção] | PSF License | Scripts de auditoria e comparador/API | A versão do runtime atual não prova ambiente de produção |
| FastAPI | [EVIDÊNCIA DA EMPRESA — congelar versão] | MIT | API do protótipo | API local experimental |
| Uvicorn | [EVIDÊNCIA DA EMPRESA — congelar versão] | BSD-3-Clause | Servidor ASGI local | API local experimental |
| Biblioteca padrão Python | versão ligada ao runtime | PSF License | Parsing/estatística/serialização dos scripts | Usada no comparador |
| Outras | [COMPLETAR por inventário/lockfile do ambiente final] | [COMPLETAR] | [COMPLETAR] | Não inventar |

Registrar hash do arquivo de dependências e licenças exatas do ambiente congelado. `requirements-api.txt` atual contém dependências mínimas do serviço, não um inventário completo do ambiente de treino/produção.

### 3.2 Metodologias testadas e escolhidas

| Metodologia | Testada no alvo de avaliação? | Modelo final? | Justificativa |
|---|---|---|---|
| Comparador ITBI por mediana de preço unitário | Testado somente como referência temporal de transações | Não como avaliação operacional; candidato exploratório ITBI | Simples, rastreável e sem atributos inventados; erro elevado e domínio de área/segmento limitado |
| Regressão linear/regularizada | Não validada para avaliação nos dados atuais | Não | Não há rótulos de avaliação elegíveis |
| Random Forest / Gradient Boosting / XGBoost / LightGBM / CatBoost / SVR / redes neurais | Não validar sobre base legada ou rótulo fiscal | Não | Resultados antigos não são confiáveis; nova comparação depende de alvo e dataset válidos |
| Modelo de oferta | Não treinado | Não | CSV de ofertas tem 0 linhas |

No relatório assinado, declarar apenas métodos efetivamente executados na versão do modelo apresentada. Escolher modelo final e alvo só depois de comparação apropriada; não declarar algoritmo selecionado com desempenho de uma natureza de preço diferente.

### 3.3 Hiperparâmetros e explicabilidade

Comparador determinístico ITBI: parâmetros conhecidos incluem área de entrada 15–1.000 m², padrões IPTU 20–25, suporte mínimo 30, venda/compra, status SQL ativo, uso IPTU 20, transmissão 100%, mediana e P10/P90. Não são hiperparâmetros treinados.

Algoritmo de ML final: [NÃO EXISTE para valor de avaliação no repositório.] Se for criado, listar algoritmo/etapa, hiperparâmetro, valor e critério de definição, além do método de explicabilidade e limites da interpretação.

### 3.4 Importância e contribuição das variáveis

No comparador ITBI não há importância de features de um modelo supervisionado. Área multiplica a taxa mediana; CEP/código podem segmentar os comparáveis, mas não se deve interpretar como efeito causal. Para ML futuro, calcular contribuição em teste independente e medir ganho contra baseline sem atributos estimados.

## 4. Recursos tecnológicos e segurança

### 4.1 Software, aplicativos e ambientes

**Conhecido:** HTML/JavaScript para interface; FastAPI/Uvicorn para endpoint local; scripts Python para auditoria/comparador.  
**Completar:** versões, ambientes de desenvolvimento/homologação/produção, ferramentas de execução, sistema operacional e licenças com base em inventário real.

### 4.2 Linguagens

Python e JavaScript/HTML no protótipo. [EVIDÊNCIA DA EMPRESA — identificar versões e ambientes de execução usados na versão apresentada.]

### 4.3 Infraestrutura

**O repositório comprova somente serviço local de desenvolvimento**, não infraestrutura empresarial contratada, hospedagem CAIXA, alta disponibilidade, segregação, segurança, backup, recuperação ou continuidade.

Preencher cada item com nome do provedor/serviço, região, contrato/ordem, arquitetura, capacidade, configuração e evidência/teste:

| Item do formulário | Evidência empresarial necessária |
|---|---|
| Ambiente de hospedagem e provedor/região | Inventário, contrato e arquitetura existente |
| Banco de dados/armazenamento | Tecnologia, localização, criptografia, acesso, retenção e evidência |
| Ambientes e segregação | Dev/homologação/produção e controles de promoção |
| Monitoramento/logs | Ferramentas, eventos registrados, acesso e retenção |
| Backup/restauração | Frequência, escopo, retenção e teste de restauração |
| Continuidade | RTO/RPO ou parâmetros internos, responsáveis, contingência e teste |
| Segurança | Gestão de identidade/acesso, criptografia, gestão de chaves, vulnerabilidades e incidentes |
| Justificativa de capacidade | Carga esperada, disponibilidade, escalabilidade e requisitos da CAIXA |

Não marcar esta seção como atendida até possuir infraestrutura necessária para prosseguir e evidência correspondente, conforme a resposta compartilhada. O esclarecimento não foi verificado oficialmente.

### 4.4 IA para leitura de matrículas

O PDF local reproduz o requisito do TR 7.2 de usar ferramenta de IA devidamente configurada para leitura automatizada de matrículas, com responsabilidade pela guarda e segurança dos dados.

**Situação do repositório: não implementado e sem evidência de ferramenta configurada.**  
Preencher solução, fornecedor, versão, tecnologia (OCR/NLP/LLM ou equivalente), campos extraídos, validação por amostra, taxa de acerto com denominador e métricas, limites de confiança, revisão humana, exceções, armazenamento/retenção e segurança.

Não declarar que esta interface/comparador ou uso genérico de IA atende a leitura de matrícula. Antes de processar documentos reais, definir ambiente autorizado e controles de dados.

### 4.5 Segurança da informação e proteção de dados

Para acesso, logs, criptografia em trânsito/repouso, segregação, incidentes, LGPD, descarte seguro e justificativa: [EVIDÊNCIA DA EMPRESA — política formal, controles implantados, responsável e teste.] O código local não comprova atendimento. Não incluir dados pessoais reais em amostras de demonstração sem base legal e proteção adequadas.

### 4.6 Monitoramento

Definir métricas, frequência, base comparativa, limites de alerta/suspensão, gatilhos de recalibração, tratamento de degradação e comunicação à CAIXA. [DECISÃO DA PRECIFICADORA + EVIDÊNCIA DE PROCESSO.] Não declarar desempenho monitorado sem monitoramento executado.

### 4.7 Reprodutibilidade

Preservar dados e origem autorizada, scripts, código, dependências/licenças, parâmetros, artefato, logs, versões e exemplos de reprodução. O projeto tem scripts de auditoria e comparador; a empresa ainda deve comprovar retenção, controle de versões completo, backup e capacidade de reproduzir a versão assinada em ambiente controlado.

## 5. Ausência de preenchimento

Manter registro por campo, seção e razão. Pendências conhecidas:

| Campo/seção | Justificativa factual atual | Ação |
|---|---|---|
| Rótulos/estatísticas de avaliação | Nenhum valor de avaliação rastreável foi localizado; valores disponíveis são transação/fiscais | Escolher alvo e obter dados compatíveis ou descrever, sem equivalência, escopo alternativo autorizado |
| Estatísticas de preço de oferta | Não há anúncios no CSV/template | Só preencher após coleta legal documentada e auditoria |
| Proveniência de quartos/banheiros/vagas/elevador/áreas | Campos da planilha enriquecida sem evidência por unidade/edifício | Recuperar documentos/fontes e validar amostra |
| Estado de conservação do condomínio | Ausente nas bases; mensagem diz que houve retificação excluindo-o, ainda não confirmada no documento oficial | Confirmar versão vigente; declarar não aplicável se excluído |
| IA de leitura de matrícula | Sem implementação/evidência no repositório | Selecionar/configurar solução e validar, ou obter orientação oficial sobre interpretação antes de afirmar atendimento |
| Infraestrutura empresarial | Não comprovada por código/API local | Anexar inventário, contratos e evidências de operação/teste |
| Métricas de avaliação, seleção de algoritmo e hiperparâmetros ML | Não existe conjunto elegível de avaliação | Não declarar; preparar após definir alvo e treino válido |
| Responsáveis, empresa e assinatura | Dados pessoais/contratuais não fornecidos ao assistente | Preenchimento e assinatura pelos responsáveis autorizados |

## 6. Declarações e responsabilidades

O formulário oficial inclui declarações de veracidade, rastreabilidade, riscos/limitações, atribuições dos responsáveis, preservação e reprodução, submissão de atualizações, independência e conflito de interesses. Os responsáveis da empresa devem revisar e assinar somente as declarações que possam atestar.

**Não copiar/assinar a declaração final com as lacunas acima abertas.** A CAIXA receber o relatório não transfere a responsabilidade técnica, conforme o texto do formulário.

## 7. Assinaturas digitais

Preencher os quatro responsáveis listados no PDF oficial: modelo automatizado; análise do mercado imobiliário; inserção de dados/emissão do relatório; representante legal. Confirmar formação, registros profissionais, vínculos, independência/conflitos e assinaturas digitais exigidos.

## Pacote de evidências a anexar ou preservar para auditoria

1. Relatório técnico assinado em PDF/A, no modelo oficial e na versão vigente.
2. Dicionário/matriz de atributos com cobertura preenchida separada da cobertura validada.
3. Manifesto de cada fonte, licença/termos, data, periodicidade e hashes.
4. Base saneada versionada, regras de inclusão/exclusão e relatório quantitativo.
5. Estatísticas descritivas do conjunto efetivamente usado para treinamento.
6. Código, ambiente/dependências, parâmetros, artefato e comandos de reprodução.
7. Protocolo e resultados de treino/validação/teste, métricas e análises de viés/generalização.
8. Evidência da IA de leitura de matrícula, validação e segurança, conforme TR 7.2.
9. Evidência de infraestrutura, segurança, backup/restauração, continuidade e monitoramento.
10. Registro das pendências, decisões e justificativas — sem converter ausência de evidência em “atendido”.

## Decisões imediatas para fechar a versão a apresentar

1. Confirmar o prazo e a versão oficial do PDF/retificações; o PDF local indica envio até 30/10/2026, em PDF/A, assinado digitalmente, por e-mail.
2. Escolher explicitamente o escopo do modelo: transação ITBI, preço de oferta ou avaliação. Não misturar rótulos.
3. Se escolher preço de oferta, não usar o comparador ITBI como se fosse o modelo de oferta. Obter amostra legal e representativa; o template atual tem zero registros.
4. Se escolher avaliação, não declarar que o valor ITBI/fiscal é avaliação. É necessário um método/target que sustente essa finalidade e avaliação técnica independente; se os dados não permitem, registrar a limitação e submeter a proposta sem alegar validação inexistente.
5. Tratar infraestrutura e IA de leitura de matrículas como frentes prioritárias: o PDF do Relatório cita explicitamente IA para leitura de matrícula e segurança; o repositório ainda não demonstra esses itens.
6. Levar este rascunho aos responsáveis técnicos/legais para completar evidências e decidir se a empresa consegue assinar com veracidade.

## Referências internas

- [Avaliação de conformidade e esclarecimentos compartilhados](avaliacao_conformidade_caixa.md)
- [Diagnóstico técnico e matriz de atributos](diagnostico_tecnico_base.md)
- [Mapa de origem dos dados para o alvo de avaliação](mapa_origem_dados_avaliacao.md)
- [Estrutura e auditoria de ofertas](modelo_ofertas.md)
- [CSV provisório e bloqueios de treinamento](uso_csv_modelagem.md)
