$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
$pythonProjeto = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $pythonProjeto)) { throw 'Execute instalar.ps1 primeiro.' }
New-Item -ItemType Directory -Force dados\mongo,dados\redis,logs,evidencias | Out-Null

function Testar-Porta([int]$Porta) {
    $tcp = New-Object System.Net.Sockets.TcpClient
    try { $tcp.Connect('127.0.0.1', $Porta); return $true }
    catch { return $false }
    finally { $tcp.Dispose() }
}

if (-not (Testar-Porta 27017)) {
    $mongodProjeto = Get-ChildItem '.local\mongodb' -Recurse -Filter mongod.exe | Select-Object -First 1
    if (-not $mongodProjeto) { throw 'MongoDB ausente. Execute instalar.ps1.' }
    $pastaMongo = Join-Path $PSScriptRoot 'dados\mongo'
    $logMongo = Join-Path $PSScriptRoot 'logs\mongodb.log'
    Start-Process -FilePath $mongodProjeto.FullName -WindowStyle Hidden -WorkingDirectory $PSScriptRoot -ArgumentList @('--dbpath', ('"{0}"' -f $pastaMongo), '--logpath', ('"{0}"' -f $logMongo), '--logappend', '--bind_ip', '127.0.0.1', '--port', '27017') | Out-Null
}
if (-not (Testar-Porta 6379)) {
    $redisProjeto = Get-ChildItem '.local\redis' -Recurse -Filter redis-server.exe | Select-Object -First 1
    if (-not $redisProjeto) { throw 'Redis ausente. Execute instalar.ps1.' }
    # Caminhos relativos funcionam também no runtime Cygwin desta compilação.
    Start-Process -FilePath $redisProjeto.FullName -WindowStyle Hidden -WorkingDirectory (Join-Path $PSScriptRoot 'dados\redis') -ArgumentList @('--bind', '127.0.0.1', '--port', '6379', '--protected-mode', 'yes', '--appendonly', 'yes', '--dir', '.', '--logfile', 'redis.log') | Out-Null
}
$pronto = $false
for ($tentativa = 0; $tentativa -lt 30; $tentativa++) {
    if ((Testar-Porta 27017) -and (Testar-Porta 6379)) { $pronto = $true; break }
    Start-Sleep -Seconds 1
}
if (-not $pronto) { throw 'Os bancos nao iniciaram. Consulte logs\mongodb.log e dados\redis\redis.log.' }
& $pythonProjeto main.py verificar
if ($LASTEXITCODE -ne 0) { throw 'Falha na verificacao dos bancos.' }
