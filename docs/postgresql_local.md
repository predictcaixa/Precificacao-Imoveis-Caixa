# Configuração local do PostgreSQL para o AVM

O pgAdmin é o cliente de administração. O AVM conecta-se ao serviço PostgreSQL por `localhost:5432`; não se conecta ao pgAdmin. O serviço local PostgreSQL 18 foi verificado em execução. O usuário precisa autenticar com a senha definida na instalação.

## 1. Criar um usuário dedicado e o banco no pgAdmin

1. Abra o pgAdmin e conecte ao servidor PostgreSQL local com a conta administradora criada durante a instalação.
2. Em **Login/Group Roles**, clique com o botão direito e escolha **Create > Login/Group Role**.
3. Na aba **General**, use `avm_app` como nome.
4. Na aba **Definition**, defina uma senha forte e guarde-a no gerenciador de senhas institucional.
5. Na aba **Privileges**, habilite **Can login?**. Deixe **Superuser**, **Create databases** e **Create roles** desabilitados.
6. Salve a função.
7. Em **Databases**, clique com o botão direito e escolha **Create > Database**.
8. Use `avm_precificacao` como nome e selecione `avm_app` como proprietário. Salve.

O PostgreSQL já está instalado e o serviço está ativo; não reinstale o servidor nem compartilhe a senha com o projeto ou pelo chat.

## 2. Testar a conexão no PowerShell

Na raiz do repositório, defina a senha sem exibi-la na tela e verifique a conta/banco. A senha não é escrita em arquivo nem incluída na URL:

```powershell
$securePassword = Read-Host "Senha do usuario avm_app" -AsSecureString
$passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
try {
    $env:PGPASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
    Remove-Variable securePassword, passwordPointer
}

$env:AVM_DATABASE_URL = "postgresql://avm_app@localhost:5432/avm_precificacao"
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -w `
    -h localhost -p 5432 -U avm_app -d avm_precificacao `
    -c "SELECT current_database(), current_user;"
```

O resultado esperado informa `avm_precificacao` e `avm_app`. Se `psql` não estiver nesse caminho, localize `psql.exe` na pasta `bin` da sua instalação PostgreSQL.

## 3. Iniciar e confirmar o AVM

Na mesma janela do PowerShell, ainda na raiz do projeto:

```powershell
py -3.13 -m pip install -r requirements-api.txt
.\iniciar_avm.ps1
```

O iniciador repassa a configuração ao processo da API, remove as variáveis de senha da sessão do PowerShell e abre a interface na porta 8001. Mantenha aberta a janela da API. Se a porta 8001 estiver ocupada, encerre somente o servidor antigo do projeto no terminal em que ele foi iniciado; o script não mata processos.

Na interface, abra **Cálculo de preço ITBI**. O histórico deve indicar **PostgreSQL**. Também é possível confirmar no PowerShell:

```powershell
Invoke-RestMethod "http://localhost:8001/avm/imports?limit=1" |
    Select-Object database, imports
```

Com a primeira inicialização da API, as tabelas `avm_imports` e `avm_import_rows` são criadas automaticamente no banco. Para conferi-las no pgAdmin, abra o Query Tool conectado a `avm_precificacao` e execute:

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('avm_imports', 'avm_import_rows')
ORDER BY table_name;
```

## Senha e desligamento

Não salve `PGPASSWORD`, a URL com senha, nem a senha em `.env`, scripts, capturas de tela ou Git. A URL usada pelo AVM não contém a senha. Para remover as variáveis da sessão do PowerShell ao encerrar o uso:

```powershell
Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
Remove-Item Env:AVM_DATABASE_URL -ErrorAction SilentlyContinue
```

O iniciador também limpa essas variáveis na janela em que é executado depois que o processo do servidor é iniciado.

## Histórico antigo SQLite

A aplicação grava novos dados no PostgreSQL quando `AVM_DATABASE_URL` está definida. A migração antiga do SQLite só é necessária se `dados/avm_uploads.sqlite3` existir e contiver histórico que deve ser preservado. Use o script `scripts/migrate_avm_sqlite_to_postgres.py` somente depois de criar o banco PostgreSQL vazio e configurar as variáveis de ambiente. O script interrompe a migração se o destino já contiver importações e conserva o arquivo SQLite original.
