# Estrutura do projeto

Este documento identifica onde ficam os componentes ativos, os dados e os arquivos de apoio. Os arquivos de entrada são preservados em seus locais; os artefatos derivados devem ficar separados dos originais.

```text
.
├── main.py                 # API FastAPI
├── index.html              # Interface web
├── iniciar_avm.ps1         # Inicialização local do AVM com PostgreSQL
├── requirements-api.txt    # Dependências da API e inferência
├── requirements-avm.txt    # Dependências do fluxo experimental de treinamento
├── scripts/                # Auditorias, importação, migração e pipelines
│   ├── dados/              # Relatórios derivados dos scripts
│   └── offer_avm/          # Código auxiliar do AVM de ofertas
├── dados/                  # Planilhas de origem e dados de trabalho
│   └── derivados/          # CSVs e catálogos produzidos por scripts
├── models/                 # Artefatos usados pelos fluxos experimentais
│   └── offer_avm/          # Modelos de oferta carregados pela API
├── docs/                   # Diagnósticos, decisões e instruções operacionais
├── arquivo_legado/         # Código e artefatos antigos, somente para consulta
├── test_*.py               # Testes do projeto na raiz
├── .env                    # Configuração local; não deve ser versionada
└── README.md               # Visão geral e comandos principais
```

## Caminhos de execução

- Para iniciar o sistema localmente, configure `AVM_DATABASE_URL` e `PGPASSWORD` no PowerShell e execute `./iniciar_avm.ps1`.
- A API importa módulos de `scripts/` diretamente; mantenha a raiz do projeto como diretório de trabalho ao executá-la.
- A interface é o arquivo `index.html` na raiz. Ela busca a API local na porta 8001.
- A planilha de ofertas usada no fluxo de treinamento e disponibilizada para download é `dados/30.10.2026.xlsx`.
- As importações feitas pela interface são armazenadas no PostgreSQL configurado. O arquivo `dados/avm_uploads.sqlite3` é o armazenamento local anterior, útil apenas para consulta ou migração explícita.

## Pacote para deploy

Gere as pastas independentes de publicação a partir da raiz do repositório:

```powershell
python -B scripts\package_deploy.py --output deploy --api-url https://URL-PUBLICA-DA-API
```

O resultado contém `deploy/frontend/` para hospedagem estática e `deploy/backend/` para o serviço Python. O backend inclui scripts, modelos e os dados exigidos pelos endpoints; o frontend inclui a interface, o catálogo documentado, o modelo de planilha e `30.10.2026.xlsx`. O pacote não copia `.env` nem o banco SQLite local. Configure `AVM_DATABASE_URL` no ambiente do serviço e `AVM_CORS_ORIGINS` com o domínio do frontend, separados por vírgula se houver mais de um. O destino precisa ainda não existir para evitar sobrescrever um pacote anterior.

## Cuidados ao manter a estrutura

- Não misture arquivos de origem e resultados: coloque resultados reproduzíveis em `dados/derivados/` ou `scripts/dados/`, conforme sejam dados ou relatórios de execução.
- Não mova `main.py`, `index.html`, `scripts/` ou `models/` sem atualizar os caminhos de inicialização, carregamento e interface.
- `.venv/`, `venv/`, `__pycache__/` e arquivos SQLite auxiliares são locais/gerados e não fazem parte da estrutura de código a compartilhar.
- Mantenha credenciais em configuração local ignorada pelo Git. Não copie valores de `.env` para documentação, exemplos ou logs.
- `arquivo_legado/` não é fonte para treinamento ou execução da API atual.
