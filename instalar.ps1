$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$ProgressPreference = 'SilentlyContinue'
New-Item -ItemType Directory -Force .local\downloads,.local\mongodb,.local\redis | Out-Null
$pythonProjeto = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'
if (-not (Test-Path $pythonProjeto)) {
    & winget install --id Python.Python.3.13 --exact --source winget --scope user --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar Python pelo winget.' }
}
if (-not (Test-Path $pythonProjeto)) { throw 'Python 3.13 nao encontrado na pasta padrao do usuario.' }
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    & $pythonProjeto -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao criar ambiente virtual.' }
}
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar bibliotecas.' }

if (-not (Get-ChildItem '.local\mongodb' -Recurse -Filter mongod.exe)) {
    $urlMongo = 'https://fastdl.mongodb.org/windows/mongodb-windows-x86_64-8.0.34.zip'
    Invoke-WebRequest $urlMongo -OutFile '.local\downloads\mongodb.zip' -UseBasicParsing
    Invoke-WebRequest "$urlMongo.sha256" -OutFile '.local\downloads\mongodb.sha256' -UseBasicParsing
    $hashMongo = ((Get-Content '.local\downloads\mongodb.sha256' -Raw).Trim() -split '\s+')[0]
    if ((Get-FileHash '.local\downloads\mongodb.zip' -Algorithm SHA256).Hash -ne $hashMongo) { throw 'SHA256 MongoDB divergente.' }
    Expand-Archive '.local\downloads\mongodb.zip' -DestinationPath '.local\mongodb' -Force
}
if (-not (Get-ChildItem '.local\redis' -Recurse -Filter redis-server.exe)) {
    $urlRedis = 'https://github.com/redis-windows/redis-windows/releases/download/8.10.3/Redis-8.10.3-Windows-x64-cygwin.zip'
    Invoke-WebRequest $urlRedis -OutFile '.local\downloads\redis.zip' -UseBasicParsing
    $hashRedis = '8000848c48668c8cd32f21386ce951d0e02c1aefae39443ab9d3de11ff8ebf9e'
    if ((Get-FileHash '.local\downloads\redis.zip' -Algorithm SHA256).Hash -ne $hashRedis) { throw 'SHA256 Redis divergente.' }
    Expand-Archive '.local\downloads\redis.zip' -DestinationPath '.local\redis' -Force
}
& "$PSScriptRoot\iniciar.ps1"
Write-Host 'Instalacao concluida. Abra APRESENTAR.cmd para executar o projeto.'
