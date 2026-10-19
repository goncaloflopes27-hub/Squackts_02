[CmdletBinding()]
param([switch]$SkipBuild)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

if (-not $SkipBuild) {
    & (Join-Path $PSScriptRoot 'build_windows.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'Falha no build Windows.' }
}

$bundle = Join-Path $projectRoot 'dist\SquackTS\SquackTS.exe'
if (-not (Test-Path -LiteralPath $bundle)) { throw 'Distribuicao Windows ausente. Execute build_windows.ps1.' }
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    $python = (Get-Command python -ErrorAction Stop).Source
}
$version = (& $python -c 'from scripts.build_assets import app_version; print(app_version())').Trim()
if ($LASTEXITCODE -ne 0 -or $version -notmatch '^\d+\.\d+\.\d+$') { throw 'Versao da app invalida.' }

$compiler = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'
if (-not (Test-Path -LiteralPath $compiler)) {
    $found = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($found) { $compiler = $found.Source }
    else { throw 'Inno Setup 6 nao encontrado. Instale-o no computador de build.' }
}
& $compiler "/DAppVersion=$version" (Join-Path $projectRoot 'packaging\windows.iss')
if ($LASTEXITCODE -ne 0) { throw 'Falha ao compilar o instalador.' }
$installer = Join-Path $projectRoot "dist\installer\SquackTS-Setup-$version-x64.exe"
if (-not (Test-Path -LiteralPath $installer)) { throw 'O compilador nao produziu o instalador.' }
Write-Host "Instalador criado: $installer"
