# Deploy da interface e API na Vercel com Supabase

O pacote inclui a interface estática e a API FastAPI no mesmo serviço. A tela é servida em `/`, o estado do serviço em `/health`, e o Swagger em `/docs`.

Para caber no limite de tamanho das funções Vercel, o pacote gerado inclui somente o modelo Random Forest para inferência e dependências reduzidas. Os pacotes locais continuam podendo usar os três modelos. Na Vercel, configure `deploy/api` como **Root Directory** e use `AVM_DEFAULT_MODEL=random_forest`; esse é também o padrão detectado pelo runtime Vercel.

## Gerar o pacote Vercel

Gere ou atualize o pacote sanitizado em `deploy/api` e envie a pasta atualizada ao GitHub:

```powershell
py -3.13 -B scripts\package_deploy.py --replace
```

O pacote contém `index.html`, `main.py`, dependências reduzidas, módulos da API, o artefato Random Forest e somente relatórios agregados. Não copia `.env`, SQLite, uploads, planilhas-fonte ou Uvicorn (a Vercel fornece o runtime ASGI).

## Variáveis de ambiente na Vercel

Cadastre no projeto Vercel:

- `DATABASE_URL`: URL PostgreSQL do Supabase com SSL; use um pooler compatível com serverless.
- `AVM_DEFAULT_MODEL=random_forest`
- `AVM_OUTPUT_ADJUSTMENT_FACTOR=1.0`

O código aceita `DATABASE_URL` e mantém `AVM_DATABASE_URL` como alias de maior prioridade. O valor fica como variável secreta, nunca no GitHub, no frontend ou em `deploy/api`. Não use SQLite em produção na Vercel, pois o disco da função não é persistente. Como credenciais foram expostas anteriormente, rotacione-as no Supabase e configure somente credenciais novas.

O `.python-version` gerado fixa Python 3.13. As variáveis definidas no painel prevalecem sobre os padrões do código.

O início da API cria as tabelas `avm_imports` e `avm_import_rows` se ainda não existirem. A migration em `supabase/migrations/` também descreve o schema para a integração GitHub do Supabase. As tabelas usam RLS sem políticas públicas; a API conecta ao banco pelo backend.

## Comportamento e limitações

Na Vercel, somente Random Forest é carregado; CatBoost e XGBoost permanecem disponíveis no ambiente local completo. A previsão é uma estimativa experimental do alvo proxy `90% × OFERTA`, não uma avaliação aprovada. Quando a oferta é enviada, a API retorna separadamente o cálculo aritmético de `90% × OFERTA`. A coluna `AVALIACAO` da planilha de comparação é apenas valor de referência e não entra como dado de entrada nem como alvo do modelo atual.

Depois de gerar a planilha com as previsoes do endpoint, a ferramenta offline abaixo substitui a coluna Guilherme, registra o calculo direto da oferta em coluna separada e colore previsoes a ate 7% de pelo menos um colega. Ela requer a planilha de comparacao e a planilha de resultado da API; esses dados de referencia nao sao enviados nem embutidos no servico de deploy.

```powershell
py -3.13 -B scripts\build_peer_comparison_workbook.py `
  dados\derivados\TESTE_comp.xlsx `
  dados\derivados\TESTE_deploy_resultado_avm.xlsx `
  --model-label Random-Forest `
  --tolerance-percent 7 `
  --output dados\derivados\TESTE_comp_Guilherme_Random-Forest_7pct.xlsx
```

Verde significa proximidade de ate 7% com ao menos uma previsao de colega; amarelo significa que nenhum resultado ficou nessa tolerancia. A cor mede alinhamento com colegas, nao acuracia contra uma avaliacao independente.

## Teste temporario sem login

O login permanece desativado nesta fase, conforme solicitado para o teste do colega. O servico aceita chamadas publicas enquanto estiver exposto; use dados de teste e remova a exposicao quando a validacao terminar. O historico de importacao e acessivel pelas rotas da API.

Depois do deploy, confira `GET /`, `GET /health`, `GET /modelo/info`, `POST /predict`, `POST /predict/batch`, `POST /predict/workbook` e o upload/histórico pela própria interface ou por um cliente HTTP. `/predict/workbook` recebe os dados manuais e devolve um XLSX com o layout do arquivo de teste e as quatro colunas de saída. No log de inicialização confirme `Armazenamento de importações conectado: postgresql` e o carregamento do modelo AVM Random Forest.

## Supabase e GitHub

A integracao GitHub do Supabase aplica migrations presentes em `supabase/`; ela nao hospeda este processo Python. A Vercel publica a API e a interface a partir da pasta `deploy/api`. Defina `DATABASE_URL` nas variaveis de ambiente do projeto Vercel, nao apenas como segredo de GitHub Actions.

Se o Supabase ja tiver as tabelas porque a API foi iniciada antes, a migration usa `IF NOT EXISTS` e habilita RLS sem adicionar politicas ao acesso anonimo. Confira o historico de migrations do projeto antes de ativa-la na branch de producao.

## Itens operacionais

- Python 3.13 e dependencias listadas em `requirements.txt`.
- PostgreSQL Supabase alcancavel pelo host, com SSL.
- Backup/recovery do banco e politica de retencao dos uploads antes de usar dados reais.
- `deploy/` pode ser enviado ao GitHub depois de revisar os arquivos gerados; o `.env` e o banco local permanecem ignorados.

As previsoes continuam experimentais e nao equivalem a avaliacao homologada pela CAIXA.
