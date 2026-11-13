# Precificação de imóveis — protótipo técnico

Este repositório reúne um protótipo de API de precificação e os dados de trabalho recebidos para avaliar sua adequação ao desenvolvimento de um AVM. **O sistema ainda não está apto a emitir estimativas para uso operacional.** Há agora uma referência experimental de transações ITBI para análise exploratória, separada dos endpoints de avaliação e sem aprovação da CAIXA.



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
