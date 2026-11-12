# Deploy da interface e API com Supabase

O pacote inclui a interface estática e a API FastAPI no mesmo serviço. A tela é servida em `/`, o estado do serviço em `/health`, e o Swagger em `/docs`.

## Pacote versionado no GitHub

Gere o pacote sanitizado em `deploy/api`:

```powershell
py -3.13 -B scripts\package_deploy.py
```

Configure o serviço Python ligado ao repositório GitHub com `deploy/api` como diretório raiz. O pacote contém `index.html`, `main.py`, `requirements.txt`, `Procfile`, os módulos da API, os modelos de inferência e somente relatórios agregados. Não copia `.env`, SQLite, uploads nem planilhas-fonte.

## Variaveis do servico da API

No painel do host da API, cadastre `DATABASE_URL` com a connection string Postgres copiada do painel Supabase em **Connect**. O codigo aceita `DATABASE_URL` e mantem `AVM_DATABASE_URL` como alias de maior prioridade. O valor fica como variavel secreta do host, nunca no GitHub, no frontend ou em `deploy/api`.

No mesmo painel, configure `AVM_DEFAULT_MODEL=catboost` e `AVM_OUTPUT_ADJUSTMENT_FACTOR=1.0`. Se ainda existir a variavel antiga com `1.1833`, substitua-a por `1.0`; variaveis definidas no host prevalecem sobre o valor padrao do codigo.

O modelo experimental padrao da API e `catboost`, configurado por `AVM_DEFAULT_MODEL=catboost`; tambem e possivel escolher `xgboost` ou `random_forest`. O fator `AVM_OUTPUT_ADJUSTMENT_FACTOR` tem padrao `1.0`, sem multiplicacao adicional. No conjunto `TESTE_comp.xlsx`, o fator 1.1833 reduziu o MAPE contra a media de Januario/Analise, mas aumentou o MAPE contra `AVALIACAO` de 16,66% para 20,51%, por isso deixou de ser o padrao. Um CatBoost experimental treinado para imitar a media dos dois colegas foi avaliado por leave-one-out em 28 casos: MAPE de 15,22% contra a media dos colegas e 20,21% contra `AVALIACAO`; nao foi aprovado para substituir o modelo padrao. O alvo de treino operacional continua sendo 90% da oferta, nao uma avaliacao confirmada.

Use a string com `sslmode=require`. Para um backend persistente, o Supabase recomenda a conexao direta; se o host da API for somente IPv4, use o Session Pooler. Use o Transaction Pooler para funcoes serverless/edge e confirme a compatibilidade com prepared statements. Copie host, porta e usuario exatamente do painel Supabase, pois variam conforme o metodo escolhido.

O inicio da API cria as tabelas `avm_imports` e `avm_import_rows` se ainda nao existirem. A migration em `supabase/migrations/` tambem descreve o schema para a integracao GitHub do Supabase. As tabelas usam RLS sem politicas publicas; a API conecta ao banco pelo backend.

## Validacao comparativa aprovada

O fluxo padrao usa CatBoost sem multiplicador adicional (`AVM_OUTPUT_ADJUSTMENT_FACTOR=1.0`) e identifica a previsao como estimativa experimental do alvo proxy `90% × OFERTA`. Quando a oferta e enviada, a API retorna separadamente o calculo aritmetico de `90% × OFERTA`, que nao e uma previsao CatBoost. A coluna `AVALIACAO` da planilha de comparacao e apenas valor de referencia e nao entra como dado de entrada nem como alvo do modelo atual.

Depois de gerar a planilha com as previsoes do endpoint, a ferramenta offline abaixo substitui a coluna Guilherme, registra o calculo direto da oferta em coluna separada e colore previsoes a ate 7% de pelo menos um colega. Ela requer a planilha de comparacao e a planilha de resultado da API; esses dados de referencia nao sao enviados nem embutidos no servico de deploy.

```powershell
py -3.13 -B scripts\build_peer_comparison_workbook.py `
  dados\derivados\TESTE_comp.xlsx `
  dados\derivados\TESTE_deploy_resultado_avm.xlsx `
  --model-label CatBoost `
  --tolerance-percent 7 `
  --output dados\derivados\TESTE_comp_Guilherme_CatBoost_7pct.xlsx
```

Verde significa proximidade de ate 7% com ao menos uma previsao de colega; amarelo significa que nenhum resultado ficou nessa tolerancia. A cor mede alinhamento com colegas, nao acuracia contra uma avaliacao independente.

## Teste temporario sem login

O login permanece desativado nesta fase, conforme solicitado para o teste do colega. O servico aceita chamadas publicas enquanto estiver exposto; use dados de teste e remova a exposicao quando a validacao terminar. O historico de importacao e acessivel pelas rotas da API.

Depois do deploy, confira `GET /`, `GET /health`, `GET /modelo/info`, `POST /predict`, `POST /predict/batch`, `POST /predict/workbook` e o upload/histórico pela própria interface ou por um cliente HTTP. `/predict/workbook` recebe os dados manuais e devolve um XLSX com o layout do arquivo de teste e as quatro colunas de saída. No log de inicialização confirme `Armazenamento de importações conectado: postgresql` e o carregamento dos modelos AVM.

## Supabase e GitHub

A integracao GitHub do Supabase aplica migrations presentes em `supabase/`; ela nao hospeda este processo Python. O servico FastAPI continua sendo publicado a partir do mesmo repositorio, mas como servico web separado. Defina `DATABASE_URL` no ambiente desse host, nao apenas como segredo de GitHub Actions.

Se o Supabase ja tiver as tabelas porque a API foi iniciada antes, a migration usa `IF NOT EXISTS` e habilita RLS sem adicionar politicas ao acesso anonimo. Confira o historico de migrations do projeto antes de ativa-la na branch de producao.

## Itens operacionais

- Python 3.13 e dependencias listadas em `requirements.txt`.
- Start command do `Procfile`: `uvicorn main:app --host 0.0.0.0 --port $PORT`.
- PostgreSQL Supabase alcancavel pelo host, com SSL.
- Backup/recovery do banco e politica de retencao dos uploads antes de usar dados reais.
- `deploy/` pode ser enviado ao GitHub depois de revisar os arquivos gerados; o `.env` e o banco local permanecem ignorados.

As previsoes continuam experimentais e nao equivalem a avaliacao homologada pela CAIXA.
