# Deploy da API com Supabase

O deploy inclui somente a API FastAPI. O frontend estatico fica fora deste pacote; o colega podera testar as rotas pelo Swagger em `/docs` ou por um cliente HTTP.

## Pacote versionado no GitHub

Gere o pacote sanitizado em `deploy/api`:

```powershell
py -3.13 -B scripts\package_deploy.py
```

Configure o servico Python ligado ao repositorio GitHub com `deploy/api` como diretorio raiz. O pacote contem `main.py`, `requirements.txt`, `Procfile`, os modulos da API, os modelos de inferencia e somente relatorios agregados. Nao copia `.env`, SQLite, uploads nem planilhas-fonte.

## Variaveis do servico da API

No painel do host da API, cadastre `DATABASE_URL` com a connection string Postgres copiada do painel Supabase em **Connect**. O codigo aceita `DATABASE_URL` e mantem `AVM_DATABASE_URL` como alias de maior prioridade. O valor fica como variavel secreta do host, nunca no GitHub, no frontend ou em `deploy/api`.

Use a string com `sslmode=require`. Para um backend persistente, o Supabase recomenda a conexao direta; se o host da API for somente IPv4, use o Session Pooler. Use o Transaction Pooler para funcoes serverless/edge e confirme a compatibilidade com prepared statements. Copie host, porta e usuario exatamente do painel Supabase, pois variam conforme o metodo escolhido.

O inicio da API cria as tabelas `avm_imports` e `avm_import_rows` se ainda nao existirem. A migration em `supabase/migrations/` tambem descreve o schema para a integracao GitHub do Supabase. As tabelas usam RLS sem politicas publicas; a API conecta ao banco pelo backend.

## Teste temporario sem login

O login permanece desativado nesta fase, conforme solicitado para o teste do colega. O servico aceita chamadas publicas enquanto estiver exposto; use dados de teste e remova a exposicao quando a validacao terminar. O historico de importacao e acessivel pelas rotas da API.

Depois do deploy, confira `GET /`, `GET /modelo/info`, `POST /predict`, `POST /predict/batch` e o upload/historico pelo frontend local ou cliente HTTP. No log de inicializacao confirme `Armazenamento de importacoes conectado: postgresql` e o carregamento dos modelos AVM.

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
