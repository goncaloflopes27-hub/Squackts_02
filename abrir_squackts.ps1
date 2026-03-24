[CmdletBinding()]
param(
    [string]$ProjectPath = ""
)

$ErrorActionPreference = 'Stop'

function Show-Info([string]$Message) {
    Write-Host "[Squackts] $Message" -ForegroundColor Cyan
}

function Show-ErrorAndExit([string]$Message, [int]$Code = 1) {
    Write-Host "[Squackts] ERRO: $Message" -ForegroundColor Red
    exit $Code
}

try {
    $scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

    if ([string]::IsNullOrWhiteSpace($ProjectPath)) {
        $ProjectPath = $scriptRoot
    }

    if (-not (Test-Path -LiteralPath $ProjectPath)) {
        Show-ErrorAndExit "A pasta do projeto não existe: $ProjectPath"
    }

    if (-not (Test-Path -LiteralPath (Join-Path $ProjectPath 'app.py'))) {
        Show-ErrorAndExit "Entrypoint não encontrado (app.py) em: $ProjectPath"
    }

    Set-Location -LiteralPath $ProjectPath
    Show-Info "Projeto: $ProjectPath"

    $pythonCmd = $null
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $pythonCmd = @('py', '-3')
    }
    elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $pythonCmd = @('python')
    }

    if (-not $pythonCmd) {
        Show-ErrorAndExit "Python não encontrado. Instale Python 3.11+ e marque 'Add Python to PATH'."
    }

    Show-Info "Python detetado via: $($pythonCmd -join ' ')"

    $venvPath = Join-Path $ProjectPath '.venv'
    $venvPython = Join-Path $venvPath 'Scripts\python.exe'
    $venvPip = Join-Path $venvPath 'Scripts\pip.exe'

    if (-not (Test-Path -LiteralPath $venvPython)) {
        Show-Info 'A criar ambiente virtual (.venv)...'
        if ($pythonCmd.Length -gt 1) {
            & $pythonCmd[0] $pythonCmd[1] -m venv $venvPath
        }
        else {
            & $pythonCmd[0] -m venv $venvPath
        }
        if ($LASTEXITCODE -ne 0) {
            Show-ErrorAndExit 'Falha ao criar o ambiente virtual (.venv).'
        }
    }

    $requirementsPath = Join-Path $ProjectPath 'requirements.txt'
    if (-not (Test-Path -LiteralPath $requirementsPath)) {
        Show-ErrorAndExit 'requirements.txt não encontrado na pasta do projeto.'
    }

    $requirementsHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $requirementsPath).Hash
    $hashStampPath = Join-Path $venvPath '.requirements.sha256'
    $installedHash = ''
    if (Test-Path -LiteralPath $hashStampPath) {
        $installedHash = (Get-Content -LiteralPath $hashStampPath -Raw).Trim()
    }

    if ($installedHash -ne $requirementsHash) {
        Show-Info 'A instalar/atualizar dependências...'
        & $venvPython -m pip install --upgrade pip
        if ($LASTEXITCODE -ne 0) {
            Show-ErrorAndExit 'Falha ao atualizar o pip no ambiente virtual.'
        }
        & $venvPip install -r $requirementsPath
        if ($LASTEXITCODE -ne 0) {
            Show-ErrorAndExit 'Falha ao instalar dependências de requirements.txt.'
        }
        Set-Content -LiteralPath $hashStampPath -Value $requirementsHash -Encoding UTF8
    }
    else {
        Show-Info 'Dependências já estão em dia.'
    }

    Show-Info 'A arrancar Squackts POD Manager...'
    & $venvPython app.py
    exit $LASTEXITCODE
}
catch {
    Show-ErrorAndExit $_.Exception.Message
}
