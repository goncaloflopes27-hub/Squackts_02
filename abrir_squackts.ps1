[CmdletBinding()]
param(
    [string]$ProjectPath = ""
)

$ErrorActionPreference = 'Stop'

function Show-Info([string]$Message) {
    Write-Host "[SquackTS] $Message" -ForegroundColor Cyan
}

function Show-ErrorAndExit([string]$Message, [int]$Code = 1) {
    Write-Host "[SquackTS] ERRO: $Message" -ForegroundColor Red
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

    & $venvPython -c "import sys; assert sys.version_info >= (3, 11), 'Requer Python 3.11 ou superior'"
    if ($LASTEXITCODE -ne 0) {
        Show-ErrorAndExit 'O ambiente .venv requer Python 3.11+. Recrie-o com uma versão suportada.'
    }
    $constraintsPath = Join-Path $ProjectPath 'constraints.txt'
    if (-not (Test-Path -LiteralPath $constraintsPath)) {
        Show-ErrorAndExit 'constraints.txt não encontrado na pasta do projeto.'
    }
    $requirementsHash = ((Get-FileHash -Algorithm SHA256 -LiteralPath $requirementsPath).Hash +
        (Get-FileHash -Algorithm SHA256 -LiteralPath $constraintsPath).Hash)
    $hashStampPath = Join-Path $venvPath '.requirements.sha256'
    $installedHash = ''
    if (Test-Path -LiteralPath $hashStampPath) {
        $installedHash = (Get-Content -LiteralPath $hashStampPath -Raw).Trim()
    }

    if ($installedHash -ne $requirementsHash) {
        Show-Info 'A instalar/atualizar dependências...'
        & $venvPython -m pip install --disable-pip-version-check -r $requirementsPath
        if ($LASTEXITCODE -ne 0) {
            Show-ErrorAndExit 'Falha ao instalar dependências de requirements.txt.'
        }
        & $venvPython -m pip check
        if ($LASTEXITCODE -ne 0) {
            Show-ErrorAndExit 'Dependências incompatíveis no ambiente virtual.'
        }
        Set-Content -LiteralPath $hashStampPath -Value $requirementsHash -Encoding UTF8
    }
    else {
        Show-Info 'Dependências já estão em dia.'
    }

    Show-Info 'A arrancar SquackTS...'
    & $venvPython app.py
    exit $LASTEXITCODE
}
catch {
    Show-ErrorAndExit $_.Exception.Message
}
