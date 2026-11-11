$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$port = 8001

function Clear-PostgresEnvironment {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:AVM_DATABASE_URL -ErrorAction SilentlyContinue
}

if (-not $env:AVM_DATABASE_URL) {
    throw "PostgreSQL não configurado. Defina AVM_DATABASE_URL e PGPASSWORD no PowerShell antes de iniciar; consulte a seção PostgreSQL no README.md."
}

try {
    & py -3.13 -c "import fastapi, uvicorn, catboost, xgboost, joblib, psycopg" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Dependências ausentes. Execute: py -3.13 -m pip install -r requirements-api.txt"
    }
} catch {
    throw "Python 3.13 e as dependências do AVM são necessários. $($_.Exception.Message)"
}

$listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($listeners) {
    try {
        $status = Invoke-RestMethod -Uri "http://127.0.0.1:$port/modelo/info" -TimeoutSec 3
        $storage = Invoke-RestMethod -Uri "http://127.0.0.1:$port/avm/imports?limit=1" -TimeoutSec 3
        if ($status.avm_oferta_experimental.disponivel -eq $true -and $storage.database -eq 'postgresql') {
            Write-Host "AVM já está disponível em http://localhost:$port."
            Clear-PostgresEnvironment
            Start-Process (Join-Path $projectRoot 'index.html')
            exit 0
        }
    } catch {
        # A porta está ocupada por outro serviço; não o encerre automaticamente.
    }
    $processIds = ($listeners.OwningProcess | Sort-Object -Unique) -join ', '
    throw "A porta $port está ocupada pelo processo $processIds, sem o AVM conectado ao PostgreSQL configurado. Encerre o serviço antigo no terminal dele com Ctrl+C e execute este script novamente."
}

$server = Start-Process -FilePath 'py.exe' `
    -ArgumentList @('-3.13', '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', "$port") `
    -WorkingDirectory $projectRoot `
    -PassThru
Clear-PostgresEnvironment

$ready = $false
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    Start-Sleep -Seconds 1
    if ($server.HasExited) {
        throw "A API encerrou durante a inicialização. Consulte a janela do servidor (PID $($server.Id)) para ver o erro."
    }
    try {
        $status = Invoke-RestMethod -Uri "http://127.0.0.1:$port/modelo/info" -TimeoutSec 2
        $storage = Invoke-RestMethod -Uri "http://127.0.0.1:$port/avm/imports?limit=1" -TimeoutSec 2
        if ($status.avm_oferta_experimental.disponivel -eq $true -and $storage.database -eq 'postgresql') {
            $ready = $true
            break
        }
    } catch {
        # A API ainda está iniciando.
    }
}

if (-not $ready) {
    throw "A API iniciou, mas o AVM não confirmou conexão ao PostgreSQL. Consulte a janela do servidor (PID $($server.Id))."
}

Write-Host "AVM disponível em http://localhost:$port."
Write-Host "Banco de importações: PostgreSQL configurado."
Write-Host "Mantenha aberta a janela do servidor para continuar usando o sistema."
Start-Process (Join-Path $projectRoot 'index.html')
