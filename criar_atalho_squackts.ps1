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
    $defaultProjectPath = 'C:\Users\lopes\Downloads\Squackts_02-main'

    if ([string]::IsNullOrWhiteSpace($ProjectPath)) {
        $ProjectPath = $scriptRoot
    }

    if (-not (Test-Path -LiteralPath (Join-Path $ProjectPath 'abrir_squackts.bat')) -and (Test-Path -LiteralPath (Join-Path $defaultProjectPath 'abrir_squackts.bat'))) {
        $ProjectPath = $defaultProjectPath
    }

    $launcherBat = Join-Path $ProjectPath 'abrir_squackts.bat'
    if (-not (Test-Path -LiteralPath $launcherBat)) {
        Show-ErrorAndExit "Launcher não encontrado: $launcherBat"
    }

    $desktopPath = [Environment]::GetFolderPath('Desktop')
    if (-not (Test-Path -LiteralPath $desktopPath)) {
        Show-ErrorAndExit "Não foi possível localizar o Ambiente de Trabalho: $desktopPath"
    }

    $shortcutPath = Join-Path $desktopPath 'Squackts POD Manager.lnk'
    $wshShell = New-Object -ComObject WScript.Shell
    $shortcut = $wshShell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $launcherBat
    $shortcut.WorkingDirectory = $ProjectPath
    $shortcut.WindowStyle = 1
    $shortcut.IconLocation = "%SystemRoot%\System32\SHELL32.dll,220"
    $shortcut.Description = 'Abrir Squackts POD Manager'
    $shortcut.Save()

    Show-Info "Atalho criado com sucesso: $shortcutPath"
}
catch {
    Show-ErrorAndExit $_.Exception.Message
}
