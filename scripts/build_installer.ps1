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
$metadata = Get-Content (Join-Path $projectRoot 'dist\SquackTS\build-info.json') -Raw | ConvertFrom-Json
$version = $metadata.release_version
if ($version -notmatch '^\d+\.\d+\.\d+(-rc\.\d+)?$') { throw 'Versao da app invalida.' }
$pin = Get-Content (Join-Path $projectRoot 'packaging\innosetup.json') -Raw | ConvertFrom-Json

$compiler = $env:SQUACKTS_ISCC
if (-not $compiler) { $compiler = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe' }
if (-not (Test-Path -LiteralPath $compiler)) {
    $found = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($found) { $compiler = $found.Source }
    else { throw 'Inno Setup 6 nao encontrado. Instale-o no computador de build.' }
}
# ISCC.exe has no numeric PE file version. Check the engine that actually compiles.
& $compiler "/DAppVersion=$version" "/DFileVersion=$($metadata.file_version)" (Join-Path $projectRoot 'packaging\windows.iss') | Tee-Object -Variable compilerOutput
if ($LASTEXITCODE -ne 0) { throw 'Falha ao compilar o instalador.' }
$engine = [regex]::Match(($compilerOutput -join "`n"), 'Compiler engine version: Inno Setup (\d+\.\d+\.\d+)\b')
if (-not $engine.Success) { throw 'Nao foi possivel verificar a versao do motor Inno Setup.' }
$actual = $engine.Groups[1].Value
if ($actual -ne $pin.version) { throw "Compilador Inno Setup $actual; esperado $($pin.version)." }
$installer = Join-Path $projectRoot "dist\installer\SquackTS-Setup-$version-x64.exe"
if (-not (Test-Path -LiteralPath $installer)) { throw 'O compilador nao produziu o instalador.' }
$metadata | Add-Member -NotePropertyName compiler_version -NotePropertyValue $actual
$metadata | Add-Member -NotePropertyName installer_sha256 -NotePropertyValue (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
$metadata | ConvertTo-Json | Set-Content (Join-Path $projectRoot 'dist\installer\build-info.json') -Encoding utf8
Write-Host "Instalador criado: $installer"
