[CmdletBinding()]
param([switch]$SkipChecks)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    $created = $false
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($version in @('-3.12', '-3.11')) {
            & py $version -c 'import sys' 2>$null
            if ($LASTEXITCODE -eq 0) {
                & py $version -m venv (Join-Path $projectRoot '.venv')
                if ($LASTEXITCODE -ne 0) { throw 'Falha ao criar .venv.' }
                $created = $true
                break
            }
        }
    }
    if (-not $created -and (Get-Command python -ErrorAction SilentlyContinue)) {
        & python -c 'import sys; assert (3, 11) <= sys.version_info[:2] <= (3, 12)'
        if ($LASTEXITCODE -eq 0) {
            & python -m venv (Join-Path $projectRoot '.venv')
            if ($LASTEXITCODE -ne 0) { throw 'Falha ao criar .venv.' }
            $created = $true
        }
    }
    if (-not $created) { throw 'Instale Python 3.11 ou 3.12.' }
}
& $python -c 'import sys; assert (3, 11) <= sys.version_info[:2] <= (3, 12)'
if ($LASTEXITCODE -ne 0) { throw 'O ambiente .venv deve usar Python 3.11 ou 3.12.' }
& $python -m pip install --disable-pip-version-check -r requirements-dev.txt -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar dependências fixadas.' }
if (-not $SkipChecks) {
    $previousQtPlatform = $env:QT_QPA_PLATFORM
    try {
        $env:QT_QPA_PLATFORM = 'offscreen'
        & $python -m unittest discover -s tests -v
        if ($LASTEXITCODE -ne 0) { throw 'Testes falharam.' }
        & $python -m ruff check .
        if ($LASTEXITCODE -ne 0) { throw 'Ruff falhou.' }
        & $python -m mypy
        if ($LASTEXITCODE -ne 0) { throw 'Mypy falhou.' }
    }
    finally {
        if ($null -eq $previousQtPlatform) { Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue }
        else { $env:QT_QPA_PLATFORM = $previousQtPlatform }
    }
}
& $python -m PyInstaller --noconfirm --clean packaging/Squackts.spec
if ($LASTEXITCODE -ne 0) { throw 'Empacotamento falhou.' }
Write-Host 'Distribuição criada em dist\SquackTS. Copie a pasta completa.'
