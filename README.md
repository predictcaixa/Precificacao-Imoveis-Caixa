# Precificação de imóveis — protótipo técnico

Este repositório reúne um protótipo de API de precificação e os dados de trabalho recebidos para avaliar sua adequação ao desenvolvimento de um AVM. **O sistema ainda não está apto a emitir estimativas para uso operacional.** Há agora uma referência experimental de transações ITBI para análise exploratória, separada dos endpoints de avaliação e sem aprovação da CAIXA.

## Situação atual

- A avaliação de conformidade requisito a requisito, com bloqueadores para a entrega CAIXA, está em [`docs/avaliacao_conformidade_caixa.md`](docs/avaliacao_conformidade_caixa.md).
- A matriz, o diagnóstico e a ligação auditada estão em [`docs/diagnostico_tecnico_base.md`](docs/diagnostico_tecnico_base.md).
- As fontes públicas pesquisadas, escopo de uso e limitações estão em [`docs/fontes_publicas_e_enriquecimento.md`](docs/fontes_publicas_e_enriquecimento.md).
- O mapa de origens para o alvo agora definido como avaliação está em [`docs/mapa_origem_dados_avaliacao.md`](docs/mapa_origem_dados_avaliacao.md), com versão tabular em [`mapa_origem_dados_avaliacao.csv`](dados/derivados/mapa_origem_dados_avaliacao.csv).
- O escopo alternativo de preço anunciado (oferta), o CSV de entrada e os critérios de auditoria estão em [`docs/modelo_ofertas.md`](docs/modelo_ofertas.md) e [`ofertas_imoveis_template.csv`](dados/derivados/ofertas_imoveis_template.csv). A auditoria de entrada é executada por `python -B scripts\audit_offer_csv.py`.
- A auditoria reproduzível fica em [`scripts/audit_data_sources.py`](scripts/audit_data_sources.py); o resultado atual está em [`docs/resultado_auditoria_vinculos.json`](docs/resultado_auditoria_vinculos.json).
- A conclusão sobre o alvo indicado nos PDFs e a estrutura CSV provisória estão em [`docs/uso_csv_modelagem.md`](docs/uso_csv_modelagem.md). Para regenerar os CSVs: `python -B scripts\build_modeling_csv.py`.
- O dataset provisório [`avm_dataset_provisorio.csv`](dados/derivados/avm_dataset_provisorio.csv) define o tipo de alvo como avaliação, mas deixa o valor-alvo ausente e bloqueia elegibilidade para treino; seu dicionário está em [`avm_dicionario_provisorio.csv`](dados/derivados/avm_dicionario_provisorio.csv).
- Para o alvo escolhido de avaliação, o template [`avaliacoes_imoveis_template.csv`](dados/derivados/avaliacoes_imoveis_template.csv) e o auditor `scripts\audit_evaluation_csv.py` permitem registrar e fazer triagem de rótulos autorizados, sem habilitar treinamento automaticamente. O endpoint `GET /avaliacao/auditoria` expõe essa triagem.
- O lote recebido da CAIXA é auditado por `python -B scripts\audit_caixa_validation.py`. O script gera `scripts\dados\caixa_sp_validacao_audit.json`, calcula benchmark espacial sem usar preço de venda/desconto ou campos derivados do alvo, compara área com área + quartos + vagas em casos completos e tenta holdout cronológico apenas quando `avaliacao_data` está disponível. O endpoint `GET /avaliacao/validacao-caixa` expõe cobertura, inventário de atributos e resultados; a interface apresenta esses dados em **Situação do modelo**.
- No lote atual, a data-base da avaliação está ausente e a data de coleta tem apenas um retrato; portanto, a validação temporal não pode ser executada. `data_coleta` não é substituta de `avaliacao_data`. Os atributos presentes (quartos/vagas) permanecem extraídos sem evidência independente por unidade; banheiros, elevador, idade e conservação continuam ausentes. O treino de avaliação CAIXA permanece bloqueado; a rota experimental de oferta é separada e não homologada.
- A opção **Simulação CAIXA** e `POST /avaliacao/simulacao-exploratoria` calculam uma referência matemática para área privativa usando a mediana observada do valor de avaliação por m² e exibem P10/P90 do lote. É uma função de simulação habilitada para exploração, não é uma avaliação profissional, nem libera avaliação CAIXA, treinamento de avaliação ou decisão operacional.
- A simulação independente `python -B scripts\validate_caixa_calculations.py` reavalia contagens, coberturas, razões de preço por área, divisões espaciais, métricas e comparação de atributos diretamente do CSV, além de testar as fórmulas com um exemplo sintético conhecido. A geração do catálogo executa essa verificação e interrompe se houver divergência. O resultado agregado fica em `scripts\dados\caixa_sp_validacao_calculation_check.json`; aprovação matemática não comprova qualidade dos rótulos nem libera treinamento.
- O catálogo das bases é gerado por `python -B scripts\build_data_catalog.py`; organiza fontes por natureza/alvo, registra hash/contagem/limitações sem mover arquivos originais e alimenta `GET /dados/catalogo`.
- Consulte o [catálogo documentado](docs/catalogo_bases.md) e o [inventário JSON auditável](dados/derivados/catalogo_bases.json) para ver estado e segregação atuais.
- A busca realizada por fontes públicas de avaliações no Estado de São Paulo e o pedido de acesso à informação estão em [`docs/busca_fontes_avaliacao_sp.md`](docs/busca_fontes_avaliacao_sp.md). O conjunto de desapropriações do DER/SP foi inspecionado em nível de schema e não contém coluna de valor de avaliação.
- O recorte de análise com vínculos únicos, CEP, área construída cadastral, código IPTU, rastreabilidade da linha original e campos ITBI está em `dados/derivados/itbi_registros_unicos_para_validacao.csv`. Ele não é uma base operacional nem um dataset com atributos de unidade validados.
- A base de ITBI contém valor declarado pelo contribuinte, valor venal e base de cálculo fiscal, que são campos distintos. A auditoria confirmou que `Valor Total.` da planilha enriquecida coincide com a base de cálculo fiscal em 9.658 ligações únicas; esse campo não é rótulo de avaliação.
- Os 9.660 registros da planilha `dados/22.10.2026.xlsx` foram ligados ao ITBI municipal por SQL, data e valor declarado: 9.658 vínculos únicos, 2 ambíguos, nenhum sem correspondência. Isso rastreia os campos transacionais, mas não comprova a origem dos atributos internos da unidade.
- O dataset legado `dados/dados_sp_ref.csv` contém atributos que o código anterior inferia a partir da área. Os modelos serializados e suas métricas também não têm validação adequada. Eles são artefatos experimentais, não modelos aprovados.
- Os modelos `.pkl`, metadados e gráficos do treinamento antigo foram organizados em `arquivo_legado/models/`, com inventário em [`arquivo_legado/README.md`](arquivo_legado/README.md). Eles são mantidos apenas para consulta histórica; o AVM atual usa os artefatos separados em `models/offer_avm/`.
- A API carrega somente o AVM experimental de oferta; não carrega modelos legados nem um modelo de avaliação CAIXA. O modelo experimental não equivale a uma homologação; editar metadados, por si só, não habilita avaliação operacional.
- O treinamento legado está bloqueado para impedir a reutilização do dataset derivado ou a geração de atributos não observados.
- A proveniência/licença da nova planilha de ofertas ainda não foi validada. O pipeline de `30.10.2026.xlsx` é experimental e não habilita uso operacional; o template CSV continua sendo apenas uma estrutura para coleta própria autorizada.
- O endpoint `POST /referencia/estimativa` produz um comparativo experimental com a mediana de transações ITBI por área construída cadastral. `POST /predict` e `/predict/batch` servem o alvo experimental `0,90*OFERTA`; não produzem avaliação de mercado/CAIXA. `POST /predict/workbook` aceita entradas manuais e devolve XLSX no layout de 26 colunas do arquivo de teste, com as quatro saidas nas colunas finais. `/relatorio` permanece suspenso.
- O experimento `scripts\train_itbi_experiment.py` compara medianas globais, por padrão IPTU e por CEP + padrão IPTU, com divisão temporal e exclusão de SQLs vistos no treino. O artefato `models\itbi_transaction_experiment.json` tem alvo explícito de valor declarado ITBI; não é avaliação e não habilita os endpoints operacionais. A auditoria identifica valores declarados muito baixos no holdout, mantidos sem exclusão arbitrária e sinalizados como limitação do MAPE.
- O painel **Situação do modelo** apresenta também, na mesma tela, a partição, os atributos, as métricas comparativas e os alertas de qualidade do experimento ITBI obtidos pelo catálogo (`GET /dados/catalogo`); isso não executa predição operacional nem habilita avaliação de mercado.
- A tela inicial apresenta o estado da evidência e consulta `GET /modelo/info`; a matriz separa transação, oferta e avaliação e não classifica campos enriquecidos sem proveniência como observados.
- Os módulos legados de predição em lote, métricas de modelos antigos e análise por região não são apresentados na navegação principal, pois não são alimentados por uma base validada para avaliação.
- O backtest temporal do comparador teve erro percentual absoluto mediano de 23,63%, P90 de 70,58% e cobertura observada de 80,43% para a faixa p10-p90. Esses resultados são insuficientes para avaliação operacional; mais de 73% dos casos de teste usaram fallback municipal, sem segmentação por CEP.

## Estrutura

O deploy na Vercel inclui a interface web servida pela API FastAPI, conectada ao Supabase Postgres; selecione `deploy/api` como Root Directory e siga [`docs/deploy.md`](docs/deploy.md). O pacote Vercel inclui apenas o modelo Random Forest para caber no limite das funções; localmente, continuam disponíveis os três modelos. O login permanece desativado para o teste solicitado. Configure `DATABASE_URL` como variável secreta na Vercel e não envie o `.env` ao GitHub.

```text
.
├── dados/                 # Arquivos de entrada e derivados; conferir a matriz antes de usar
├── docs/                  # Diagnóstico técnico, matriz e critérios de validação
├── models/                # Artefatos experimentais legados; não aprovados
├── main.py                # API FastAPI; predição experimental da oferta
├── train_model.py         # Treinamento bloqueado até aprovação dos dados
├── index.html             # Painel de evidências, matriz CAIXA e comparador ITBI experimental
├── extract.py             # Experimento de coleta de anúncios; não aprovado como fonte
└── levantamento_duvidas_IUP_IBAPE.md
```

## Requisitos e execução

O passo a passo para criar o usuário e o banco no pgAdmin e conectar o AVM está em [`docs/postgresql_local.md`](docs/postgresql_local.md). O serviço PostgreSQL local precisa estar em execução. Não grave senhas no repositório nem as inclua na URL.

```powershell
py -3.13 -m pip install -r requirements-api.txt

$securePassword = Read-Host "Senha do usuario avm_app" -AsSecureString
$passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
try {
    $env:PGPASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
    Remove-Variable securePassword, passwordPointer
}
$env:AVM_DATABASE_URL = "postgresql://avm_app@localhost:5432/avm_precificacao"

if (Test-Path .\dados\avm_uploads.sqlite3) {
    py -3.13 -B scripts\migrate_avm_sqlite_to_postgres.py
} else {
    Write-Host "Banco SQLite antigo não encontrado; nenhuma migração necessária."
}
.\iniciar_avm.ps1
```

O usuário `avm_app` deve ser criado no pgAdmin com privilégio de login e como proprietário de `avm_precificacao`. Altere host, porta ou nome se sua instalação usar outros valores. A migração SQLite é necessária apenas para preservar registros antigos: ela copia o histórico para um banco vazio, interrompe se o destino já contiver importações e mantém o arquivo SQLite original como cópia. Se não houver histórico a preservar, pule o comando de migração.

O iniciador usa a porta 8001 e não encerra processos existentes. Se informar que a porta 8001 está ocupada por uma API sem AVM/PostgreSQL, pare o servidor antigo do projeto no terminal dele com `Ctrl+C` e execute `.\iniciar_avm.ps1` novamente. Mantenha aberta a janela do servidor durante o uso. A API deve responder em `http://localhost:8001`; o Swagger fica em `http://localhost:8001/docs`. O iniciador exige `AVM_DATABASE_URL`, verifica as dependências e confirma que os modelos e o PostgreSQL estão disponíveis.

As planilhas processadas e os resultados das linhas são armazenados no PostgreSQL indicado por `AVM_DATABASE_URL`. O histórico da interface permite conferir contagens e excluir cada importação; a exclusão remove também as linhas relacionadas. Os dados originais da primeira aba, inclusive campos fiscais, ofertas, links e identificadores, são preservados para comparação, mas não são enviados como variáveis ao modelo. Proteja o banco e sua cópia SQLite conforme as regras internas de acesso e retenção.

`POST /predict` e `/predict/batch` servem estimativas experimentais do alvo de oferta com desconto. `POST /predict/workbook` recebe dados manuais e devolve XLSX no layout de teste. Sem oferta positiva, a API precisa do bundle AVM em `models/offer_avm/`; com oferta, calcula diretamente 90% do valor informado. Para treinar CatBoost, use Python compativel (Python <3.15) e execute `scripts\train_offer_avm.py`; consulte `/modelo/info`. A estimativa nao e avaliacao CAIXA nem preco aprovado para garantia/credito. `/relatorio` e as metricas regionais operacionais continuam suspensos.

Exemplo do corpo para `POST /referencia/estimativa`:

```json
{
  "area_construida_iptu_m2": 85,
  "cep": "01005-020",
  "codigo_padrao_iptu": "22",
  "confirmar_area_iptu": true
}
```

`area_construida_iptu_m2` deve ser exatamente a área construída do cadastro IPTU. Não informe área privativa ou total. CEP e código padrão são opcionais; sem o código, a referência usa o CEP quando há suporte mínimo suficiente e, caso contrário, o perfil municipal. O resultado contém uma mediana comparativa e a faixa p10-p90 dos preços por m² dos comparáveis; a faixa não é intervalo de confiança individual.

Para repetir a auditoria dos arquivos originais:

```powershell
python -B scripts\audit_data_sources.py --output docs\resultado_auditoria_vinculos.json
python -B scripts\audit_data_sources.py --output docs\resultado_auditoria_vinculos.json --export-analysis-csv dados\derivados\itbi_registros_unicos_para_validacao.csv
python -B scripts\experimental_reference.py --output models\itbi_reference_2026.json
python -B scripts\train_itbi_experiment.py --output models\itbi_transaction_experiment.json
python -B scripts\audit_evaluation_csv.py
python -B scripts\build_data_catalog.py
python -B -m unittest test_data_audit test_experimental_reference test_sp_model test_evaluation_csv test_data_catalog test_itbi_experiment
```

Não execute `train_model.py` esperando um novo modelo: o bloqueio é intencional até a aprovação da seleção de registros, dos atributos e do protocolo de validação.

Para a nova planilha de ofertas `dados/30.10.2026.xlsx`, há um pipeline experimental separado em `scripts/train_offer_avm.py`. Ele usa `0,90*OFERTA` como proxy de alvo, exclui todos os campos monetários fiscais e de oferta das features, treina e guarda Random Forest, CatBoost e XGBoost, reserva distritos inteiros para teste independente e gera métricas, resíduos, importância e uma cópia XLSX com estimativas. Com Python 3.13, instale `py -3.13 -m pip install -r requirements-api.txt` e execute `py -3.13 -B scripts\train_offer_avm.py`. A API carrega os três artefatos e permite escolher o algoritmo nas rotas e na interface; sem seleção, mantém o campeão por validação como padrão. Isso não altera o bloqueio das rotas operacionais de avaliação CAIXA.

Para calcular uma referência pelo terminal, acrescente `--estimate-area-iptu`, `--cep`, `--iptu-pattern` e `--confirm-area-iptu` ao comando `experimental_reference.py`. O comando recusa a estimativa se a área não for confirmada como cadastral IPTU.

## Critérios mínimos para habilitar previsões

1. Aprovar com a CAIXA o método, o uso pretendido e a definição do valor-alvo.
2. Documentar a origem, a semântica e a associação imóvel/unidade de cada atributo usado.
3. Manter atributos observados, extraídos, calculados e estimados identificados, com evidência e trilha de auditoria.
4. Validar em amostra independente e em partições temporal e geográfica, comparando com um baseline sem atributos estimados.
5. Confirmar que os mesmos atributos e evidências podem ser obtidos na operação da CAIXA.
6. Aprovar política para dados obrigatórios ausentes, limites de extrapolação, intervalos de predição e encaminhamento para análise humana.
