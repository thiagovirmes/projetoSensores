$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$arquivosEntrega = Get-ChildItem -File | Where-Object {
    $_.Extension -in '.py','.md','.txt','.ps1','.cmd','.pdf','.docx' -or $_.Name -eq '.gitignore'
} | Select-Object -ExpandProperty FullName
$itensEntrega = @($arquivosEntrega) + @(Join-Path $PSScriptRoot 'evidencias')
Compress-Archive -LiteralPath $itensEntrega -DestinationPath (Join-Path $PSScriptRoot 'entrega.zip') -Force
Write-Host 'Pacote criado: entrega.zip (fontes, documentos e evidencias; sem bancos e ambiente virtual).'
