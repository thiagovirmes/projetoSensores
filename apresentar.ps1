$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
& "$PSScriptRoot\iniciar.ps1"
& '.\.venv\Scripts\python.exe' main.py demonstrar | Tee-Object -Variable demonstracao
$codigo = $LASTEXITCODE
$demonstracao | Out-File 'evidencias\demonstracao.txt' -Encoding utf8
if ($codigo -ne 0) { throw 'A demonstracao falhou. Confira a mensagem acima.' }
Write-Host "`nEvidencia salva em evidencias\demonstracao.txt"
