# Estrutura para estimar preços anunciados

## Escopo do alvo

O primeiro modelo com dados de anúncios estima um alvo explicitamente definido. A planilha `30.10.2026.xlsx` já contém `VALOR OFERTA` e `0,90*OFERTA`; o pipeline experimental utiliza o segundo campo, após verificar que corresponde a 90% do primeiro. Esse alvo é um **proxy de oferta com desconto fixo de 10%**, não preço final de venda, valor de transação ITBI nem valor de avaliação CAIXA. O desconto não foi validado por região e não deve ser apresentado como conversão comprovada para valor de mercado.

## Painel do modelo

A tela **Modelo AVM** no sistema apresenta as métricas do teste geográfico independente e por região, a importância das variáveis, os tamanhos das partições e o estado de CatBoost reportados pelo artefato carregado em `/modelo/info`. Os arquivos em lote e os resultados das previsões ficam persistidos no PostgreSQL configurado por `AVM_DATABASE_URL`; ainda não são registrados preços reais associados a essas estimativas para monitoramento de erro/drift. Também não há retreino automático, registro de modelos ou promoção automática. Portanto, disponibilidade da rota experimental não significa operação produtiva nem homologação.

Na interface de estimativa, um mapa interativo de São Paulo mostra círculos por região com o MAPE e o tamanho da amostra do teste geográfico independente; um painel lateral ordena as regiões com maior e menor erro. Clicar em um círculo ou item seleciona a região para a estimativa. As posições dos círculos são referências aproximadas para agrupar resultados, não coordenadas de imóveis nem limites oficiais. Latitude e longitude não são solicitadas nem enviadas na previsão.

## Planilha de entrada e previsão em lote

Baixe [`dados/modelo_entrada_avm.xlsx`](../dados/modelo_entrada_avm.xlsx) pela interface ou abra o arquivo na pasta `dados`. A primeira aba, `Imoveis`, contém os cabeçalhos aceitos pela importação, duas linhas de demonstração sintéticas e uma terceira linha com atributos opcionais em branco. A aba `Instrucoes` descreve os campos e faixas. Os exemplos não são registros reais nem devem ser usados para análise de mercado. A planilha original [`dados/30.10.2026.xlsx`](../dados/30.10.2026.xlsx) também pode ser carregada diretamente: a importação usa a primeira aba (`BASE CONSOLIDADA`) e reconhece automaticamente seus cabeçalhos, como `AREA PRIV.`, `IDADE`, `QUARTOS`, `Região`, `Distrito` e as colunas de renda e área. As demais abas, como resumos, são mantidas na planilha de saída.

Para processar: preencha uma linha por apartamento, mantenha os cabeçalhos da primeira linha e selecione um ou mais arquivos `.xlsx` na tela de estimativa AVM. `area_privativa_m2` (35–1.000) e `idade_anos` (0–20) são obrigatórios. As demais variáveis podem ficar vazias; valores ausentes serão tratados pelo pipeline do modelo. Região, quando informada, deve ser uma das seis regiões listadas na aba de instruções. Na base original, CEPs numéricos de sete dígitos recebem o zero inicial ao serem preparados. Não adicione valores ITBI, venais, declarados ou de oferta como variáveis de entrada. O botão **Processar arquivo e prever** prepara e valida todas as linhas da primeira aba e executa as previsões em lotes de até 500 registros, sem retreinar o modelo. O limite é de 50.000 linhas por planilha e 20 MB por arquivo.

Cada arquivo é lido e processado isoladamente. Planilha corrompida, cabeçalhos ausentes ou linhas inválidas não interrompem os outros arquivos nem removem os registros válidos. O resultado de cada planilha é baixado separadamente; as linhas da primeira aba são mantidas e recebem `estimativa_alvo_brl`, `status_processamento` e `erro_processamento`, e as demais abas são preservadas. Linhas com área ou idade fora das faixas exigidas são mantidas no resultado com o motivo do erro, sem previsão. A API recebe somente os campos permitidos do modelo na rota de previsão, nunca as colunas fiscais ou campos adicionais como variáveis explicativas. O arquivo original não é sobrescrito.

### Persistência local das importações

Cada planilha válida gera um registro de importação e suas linhas são salvas em lotes no banco PostgreSQL indicado por `AVM_DATABASE_URL`. O histórico da tela **Cálculo de preço ITBI** lista as últimas 50 importações e seus totais; as ações **Baixar** e **Excluir** recuperam o resultado persistido ou removem o registro e todas as linhas relacionadas. Os endpoints locais são `POST /avm/imports`, `POST /avm/imports/{id}/rows`, `PATCH /avm/imports/{id}`, `GET /avm/imports`, `GET /avm/imports/{id}/rows` (paginado) e `DELETE /avm/imports/{id}`. Cada importação registra o algoritmo, estado, horários, contagem de linhas estimadas/com erro e os dados da primeira aba em JSON por linha. Essa persistência inclui as colunas originais de comparação (inclusive valores fiscais, oferta, links e identificadores), mas elas não são enviadas ao modelo nem usadas para inferência. O banco permanece no computador onde a API é executada e não é versionado; aplique os controles de acesso, retenção e exclusão exigidos para esses dados.

No Windows, instale os requisitos da API uma vez com `py -3.13 -m pip install -r requirements-api.txt`, configure `AVM_DATABASE_URL` e `PGPASSWORD`, e inicie com `.\iniciar_avm.ps1` na raiz do projeto. O script confirma que os modelos estão carregados antes de abrir o HTML. Ele usa a porta 8001; se ela estiver ocupada por uma API antiga, não encerra o processo: pare-o no terminal correspondente com `Ctrl+C` e execute o iniciador novamente. Confirme a disponibilidade em `http://localhost:8001/modelo/info`.

## Coleta própria e condições de uso

Uma resposta compartilhada por WhatsApp, ainda não conferida no canal oficial do edital, informa que não há fonte externa obrigatória/exclusiva e que a coleta própria de anúncios pode ser utilizada se a obtenção e o uso forem legais e documentados. A resposta não é uma autorização irrestrita de qualquer portal nem uma dispensa das condições da fonte. A responsabilidade legal pelo tratamento permanece com a precificadora.

Antes de iniciar coleta em cada portal:

1. Verificar e arquivar os termos de uso, licença, regras de API, direitos sobre campos/conteúdo, base legal e limitações de retenção, compartilhamento e uso para treinamento.
2. Não acessar áreas restritas nem contornar login, CAPTCHA, paywall, bloqueio, rate limit ou mecanismo de controle. Se os termos ou direitos não permitirem a coleta/armazenamento/uso desejado, não usar esse portal; buscar API/licença/autorização ou outra fonte adequada.
3. Registrar a URL e versão dos termos, data de revisão, responsável pela avaliação, método (API, captura manual ou coleta automatizada permitida), escopo/consulta, campos coletados e política de retenção/apagamento.
4. Guardar apenas os dados e evidências autorizados. Não armazenar dados pessoais desnecessários; não redistribuir conteúdo protegido.

O campo `source_license_or_permission` do template é um registro declaratório, não prova automática da legalidade. A auditoria CSV é uma triagem sintática: mesmo uma linha que passa nos campos básicos não fica legalmente autorizada nem elegível a treino sem a revisão documental e jurídica da fonte.

## Situação dos arquivos existentes

- `dados/dados_sp.csv` tem somente uma linha vazia de amostra, sem preço ou atributos utilizáveis.
- `dados/dados_sp_ref.csv` contém valores sintéticos/derivados e não é uma base de anúncios rastreável; não usar no treino.
- `dados/dados_itbi_sp.csv` e as planilhas municipais são transações/registros fiscais, não ofertas; manter fora do alvo de preço anunciado.
- `extract.py` implementa coleta de páginas de portal e usa um portal como URL padrão. A resposta compartilhada admite coleta própria em princípio, mas a existência do código não prova que aquele portal permita coleta automatizada nem que os dados possam ser armazenados/reutilizados para treino. Não executar coleta automatizada até verificar os requisitos acima para a fonte específica.
- O FipeZAP da [FIPE](https://www.fipe.org.br/pt-br/indices/fipezap/) é calculado a partir de amostras de anúncios, mas publica índices agregados; é útil para contexto de mercado, não substitui uma base de anúncios unitários para treino.

## Arquivo de entrada

Preencha `dados/derivados/ofertas_imoveis_template.csv`, uma linha por anúncio e captura/versionamento. Os campos essenciais são:

- `listing_id`: identificador interno único da captura, preferencialmente hash; não inclua nome, telefone ou dados pessoais do anunciante.
- `source_name`, `source_listing_id`, `source_url`, `source_license_or_permission`: proveniência, identificador e base de uso permitida.
- `listing_captured_at`: instante em que o anúncio foi observado; ele define a data do alvo.
- `offer_status`: `active`, `withdrawn`, `sold`, `rented` ou `unknown`. O preço que o modelo aprende continua sendo o preço pedido observado na captura, não o valor de venda/aluguel.
- `asking_price_brl`: preço pedido em reais, associado a uma evidência (`asking_price_evidence_ref`) e classificado como `observed` ou `extracted`.
- `area_value_m2` e `area_type`: valor e definição explícita (`private`, `built`, `total` ou `usable`); não combinar tipos diferentes como se fossem a mesma área.
- Atributos de unidade (`bedrooms`, `bathrooms`, `suites`, `parking_spaces`) e de edifício (`elevator`, `building_year`) com uma referência de evidência e estado. Preferir `observed`/`extracted`; qualquer `estimated` deve continuar identificável e fora do baseline.
- `location_precision`: distinguir endereço completo, rua, bairro, CEP e ponto aproximado. Não preencher coordenadas de unidade por aproximação sem armazenar a precisão.
- `record_hash`, `duplicate_group_id`, `train_eligible` e `exclusion_reason`: controles de rastreabilidade, duplicidade e elegibilidade.

As referências de evidência devem apontar para um arquivo/identificador/trecho que a organização tenha direito de guardar. Registre também o método de coleta e a evidência da revisão dos termos no processo de governança da fonte. Não copie descrições, fotos ou dados pessoais sem permissão apropriada. O template não contém linha de exemplo para não parecer dado real.

## Associação e duplicidade

1. Mesmo identificador de anúncio em capturas repetidas representa snapshots do mesmo anúncio; não tratar como imóveis independentes. Pode-se escolher uma captura por anúncio para um baseline transversal ou modelar snapshots com validação temporal agrupada por anúncio.
2. Anúncios repostados em outra URL, com texto/preço/endereço semelhantes, devem ser agrupados para revisão. A auditoria simples detecta IDs repetidos e conteúdo candidato a duplicidade, mas não resolve cópias entre portais.
3. Um anúncio de outra unidade do mesmo prédio não prova atributos da unidade-alvo. Registrar separadamente unidade, edifício e localização.
4. Armazenar o preço exatamente como capturado. Qualquer desconto derivado deve ser mantido em campo separado, com regra, período e validação próprios; não o apresentar como preço final de venda.

## Auditoria de CSV

Na raiz do projeto:

```powershell
python -B scripts\audit_offer_csv.py --input dados\derivados\ofertas_imoveis_template.csv
python -B -m unittest test_offer_csv
```

O script valida o formato e gera `dados/derivados/ofertas_auditoria.json`. Ele não faz scraping, não treina e deliberadamente nunca declara o modelo pronto: licenciamento real, veracidade, associação à unidade, representatividade e validação estatística exigem revisão específica.

## Amostra, validação e decisão do modelo

1. Não há contagem mínima universal informada pela resposta compartilhada. Demonstrar que a quantidade e composição da amostra cobrem o escopo declarado: tipo de imóvel, regiões, faixas de área/preço, tipologia, origem e períodos. Publicar células de cobertura, exclusões e segmentos sem suporte; volume bruto não prova representatividade.
2. Reunir anúncios de apartamentos de São Paulo com preço, data de captura, definição de área e localização, preservando proveniência e legalidade. Não misturar casas, escritórios, venda e aluguel sem modelos/alvos e validação próprios.
3. Deduplicar repostagens e capturas do mesmo anúncio; dividir treino/validação/teste por imóvel/anúncio e tempo, reservando período e/ou região independentes para generalização. Controlar mudanças de preço como snapshots, não observações independentes.
4. Pré-definir valores esperados internos e critérios de seleção no Relatório do Modelo. Reportar métricas apropriadas em treino, validação e teste independente — por exemplo, MAE, RMSE, MdAPE e métricas percentuais com tratamento explícito de preços baixos —, viés por segmento, estabilidade temporal, cobertura de intervalos e generalização. A resposta não estabelece limiares numéricos CAIXA; informa que critérios poderão ser definidos na homologação, fluxo pareado e monitoramento. Isso não dispensa metas internas justificadas.
5. Começar com baseline simples e interpretável; comparar outros algoritmos sob as mesmas partições. Selecionar por desempenho fora da amostra, estabilidade, generalização, interpretabilidade e compatibilidade operacional, documentando testes e trade-offs. Não reaproveitar métricas antigas não validadas.
6. Comparar modelos com e sem atributos extraídos/estimados em validação independente; medir contribuição incremental e propagação dos erros. Estimativas devem permanecer identificadas como `estimated` e separadas de valores observados.
7. Só permitir predição de oferta quando validação e disponibilidade de atributos no caso operacional estiverem confirmadas. Rotular a saída como **preço pedido anunciado estimado**, nunca como avaliação CAIXA. Qualquer uso como proxy de avaliação exige justificativa metodológica e teste pareado/independente com avaliações ou transações adequadas; não aplicar redutor uniforme.

## Atualização e versionamento

A periodicidade de atualização deve ser proposta e justificada com atualidade dos anúncios, estabilidade do mercado, cobertura e monitoramento de desempenho. A resposta compartilhada admite que a CAIXA pode reduzir a periodicidade para seis meses; portanto, demonstrar capacidade de atualizar a base/modelo nesse intervalo, ainda que se proponha outro ciclo.

Versionar cada fotografia de dados, execução, código, variáveis, algoritmo, parâmetros, métricas e relatório. Segundo a resposta compartilhada, cada atualização do modelo deve ter novo Relatório do Modelo com dados e versionamento atualizados; alterações metodológicas/estruturais também exigem atualização documental. Confirmar redação oficial, pois o esclarecimento encaminhado distingue as duas situações.

## Limite atual

A planilha `30.10.2026.xlsx` contém valores de oferta e permite um experimento técnico, mas a proveniência, a licença, a associação dos atributos à unidade e a representatividade ainda não foram validadas. O experimento não confirma esses requisitos nem habilita uso operacional. O template CSV continua disponível para coleta própria autorizada, sem implicar autorização automática de qualquer fonte.

## Pipeline experimental para `30.10.2026.xlsx`

O arquivo recebido inclui 12.762 registros e a aba `BASE CONSOLIDADA`. O script `scripts/train_offer_avm.py` implementa auditoria de rótulos e atributos, filtros de idade (0–20 anos) e área privativa (35–1.000 m²), sinalização de valores fora de faixa, análise de outliers por valor-alvo/m² e tratamento de ausentes. Para treinar, exige valor de oferta positivo e confirmação de que `0,90*OFERTA` corresponde a 90% da oferta.

O conjunto de features é uma lista permitida de características do imóvel e localização. Valor da oferta, alvo descontado, VT/VU base, valor venal, valor declarado, ITBI, matrícula, SQL, endereço e outros identificadores são explicitamente excluídos. Os campos originais da planilha são preservados na exportação.

O protocolo separa grupos inteiros de `Distrito` em treino, validação e teste independente geográfico. Random Forest, CatBoost e XGBoost são treinados e salvos como artefatos independentes; cada um tem suas próprias métricas de validação e de teste geográfico. Para manter compatibilidade, o pipeline seleciona um modelo padrão pelo MAE de validação, mas a API e o formulário permitem escolher qualquer um dos três artefatos carregados. A escolha não altera nem substitui os outros modelos. Random Forest e XGBoost aplicam imputação e one-hot encoding às categorias; CatBoost trata as categorias nativamente. A execução de treinamento exige dependências compatíveis de CatBoost e XGBoost e interrompe com erro explícito se não estiverem instaladas, em vez de publicar um conjunto incompleto. O teste independente não participa da seleção nem do ajuste de parâmetros. O relatório registra R², RMSE, MAE, MAPE, métricas por região/distrito, resíduos e importância das features. A planilha resultante acrescenta `VALOR ESTIMADO AVM` e `STATUS AVM`, distinguindo teste independente, ajuste in-sample, inferência sem rótulo e registros fora do escopo.

### Resultado histórico da execução de 31/10/2026

Foram elegíveis 9.588 registros (5.668 treino, 2.032 validação e 1.888 teste independente, separados por distrito). O teste cobriu as seis categorias de região presentes na base. Nesta máquina, Python 3.15 não tem wheel compatível do CatBoost; o relatório marca `catboost_status` como ignorado e o modelo selecionado foi Random Forest. Portanto, **os resultados abaixo não são uma comparação com CatBoost**.

| Modelo no teste independente | R² | RMSE | MAE | MAPE |
|---|---:|---:|---:|---:|
| Random Forest | 0,738 | R$ 288.398 | R$ 163.611 | 18,01% |
| Baseline (mediana do treino) | -0,096 | R$ 589.755 | R$ 384.078 | 52,28% |

O erro varia entre regiões. No teste, Zona Sul teve MAE de R$ 355.698 (MAPE 23,5%; R² 0,432), enquanto Zona Leste teve MAE de R$ 113.494 (MAPE 15,5%; R² 0,802). A categoria `Zona Leste²` foi mantida como consta na fonte e requer confirmação antes de eventual normalização. As variáveis com maior importância no Random Forest foram área privativa (56,2%), renda média (13,0%), área total (10,6%) e longitude (7,7%). Importância de árvore é indicativa, não causal. Foram sinalizados 344 valores extremos de preço por m² pelo critério 1,5×IQR, sem exclusão automática.

O teste foi independente para treinamento e seleção, mas mede a capacidade de estimar **o alvo proxy** de 90% da oferta, não valor de venda ou avaliação de mercado. Há viés negativo no teste (média de -R$ 79.596), ausência de validação temporal e dispersão de desempenho por região; não se recomenda uso decisório nem se declara desempenho aprovado.

### Comparação dos três modelos (01/11/2026)

Os três modelos foram treinados em Python 3.13.16 com CatBoost 1.2.10 e XGBoost 3.4.1. Cada candidato foi escolhido e ajustado pela validação geográfica; o conjunto independente de 1.888 imóveis/distritos foi usado somente para medir o desempenho final.

| Modelo | MAE validação | R² teste independente | RMSE teste | MAE teste | MAPE teste |
|---|---:|---:|---:|---:|---:|
| Random Forest | R$ 129.987 | 0,738 | R$ 288.398 | R$ 163.611 | 18,01% |
| CatBoost | R$ 117.380 | 0,739 | R$ 287.516 | R$ 173.896 | 19,54% |
| XGBoost | R$ 113.727 | 0,740 | R$ 287.241 | R$ 165.946 | 18,04% |

O XGBoost foi definido como padrão por obter o menor MAE na validação. Os três artefatos continuam carregados e selecionáveis; a escolha do padrão não desativa os demais. Os resultados continuam medindo o proxy de 90% da oferta, não vendas confirmadas nem avaliações CAIXA, e não significam homologação.

Instalação e execução na raiz do repositório:

```powershell
py -3.13 -m pip install -r requirements-api.txt
py -3.13 -B scripts\train_offer_avm.py
py -3.13 -m uvicorn main:app --reload --port 8001
```

O script grava os três modelos, seus resultados, o modelo padrão, relatório, importância e resíduos em `models/offer_avm/` e a planilha derivada em `dados/derivados/30.10.2026_avm_estimativas.xlsx`. O holdout é geográfico, não temporal: não foi identificada uma data de captura de anúncios. Os valores estimados no conjunto de treino são in-sample e estão marcados. O pipeline compara até três configurações por algoritmo; a API carrega os três artefatos treinados e expõe `POST /predict?modelo=random_forest`, `POST /predict?modelo=catboost` e `POST /predict?modelo=xgboost` (e os mesmos parâmetros em `/predict/batch`). Sem `modelo`, mantém o comportamento anterior e usa o campeão da validação. A tela de estimativa permite escolher o algoritmo e usa essa seleção também nas planilhas. A liberação técnica não significa validação do alvo, proveniência, direitos de uso ou desempenho; não usar as respostas como avaliação oficial, garantia ou decisão de crédito.

O relatório antigo de 31/10 continua documentado como histórico; o relatório e os três artefatos atuais foram gerados em 01/11/2026. Relatórios antigos ainda podem ser carregados, mas só disponibilizam os modelos cujos artefatos estão registrados.

### Contrato de inferência na API

Após instalar `requirements-api.txt` e iniciar `py -3.13 -m uvicorn main:app --reload --port 8001`, confirme em `http://localhost:8001/modelo/info` que `avm_oferta_experimental.disponivel` é `true` e que os três modelos estão listados. Se a porta estiver ocupada por uma API antiga, pare-a no terminal em que foi iniciada (`Ctrl+C`) antes de subir o serviço atual; uma API que responde HTTP, mas não carregou artefatos, não consegue prever. A tela agora confere essa disponibilidade antes de ler e enviar planilhas e apresenta uma orientação se o modelo não estiver carregado.

Com o serviço pronto, use `POST /predict?modelo=random_forest`, `POST /predict?modelo=catboost` ou `POST /predict?modelo=xgboost` com `area_privativa_m2`, `idade_anos`, `quartos` e `banheiros`; vagas, elevador, áreas, coordenadas, renda, CEP, região, distrito, setor e padrão IPTU podem ser enviados quando conhecidos. Sem o parâmetro `modelo`, a API utiliza XGBoost, selecionado pela validação. A rota bloqueia campos extras, inclusive valores fiscais/monetários. A idade deve estar entre 0 e 20 anos e a área privativa entre 35 e 1.000 m². `POST /predict/batch?modelo=<algoritmo>` aceita até 500 imóveis e executa a inferência em lote.

A resposta em `estimativa_alvo_brl` é somente a estimativa do alvo proxy treinado (90% do preço anunciado). A API não calcula preço de venda observado nem valor de avaliação. `GET /modelo/info` continua reportando `homologado: false` para esse AVM e mantém separada a prontidão geral do modelo de avaliação CAIXA.

Exemplo:

```powershell
curl.exe -X POST http://localhost:8001/predict `
  -H "Content-Type: application/json" `
  -d "{\"area_privativa_m2\":60,\"idade_anos\":10,\"quartos\":2,\"banheiros\":2,\"vagas\":1,\"elevador\":1,\"regiao\":\"Zona Leste\",\"distrito\":\"Cangaíba\"}"
```
