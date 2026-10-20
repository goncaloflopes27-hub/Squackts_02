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

    $launcherPath = Join-Path $ProjectPath 'SquackTS.exe'
    if (-not (Test-Path -LiteralPath $launcherPath)) {
        $launcherPath = Join-Path $ProjectPath 'abrir_squackts.bat'
    }
    if (-not (Test-Path -LiteralPath $launcherPath)) {
        Show-ErrorAndExit "Launcher não encontrado: $launcherPath"
    }

    $desktopPath = [Environment]::GetFolderPath('Desktop')
    if (-not (Test-Path -LiteralPath $desktopPath)) {
        Show-ErrorAndExit "Não foi possível localizar o Ambiente de Trabalho: $desktopPath"
    }

    $shortcutPath = Join-Path $desktopPath 'SquackTS.lnk'
    $wshShell = New-Object -ComObject WScript.Shell
    $shortcut = $wshShell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $launcherPath
    $shortcut.WorkingDirectory = $ProjectPath
    $shortcut.WindowStyle = 1
    if ([IO.Path]::GetExtension($launcherPath) -eq '.exe') {
        $shortcut.IconLocation = "$launcherPath,0"
    }
    else {
        $shortcut.IconLocation = "%SystemRoot%\System32\SHELL32.dll,220"
    }
    $shortcut.Description = 'Abrir SquackTS'
    $shortcut.Save()

    Show-Info "Atalho criado com sucesso: $shortcutPath"
}
catch {
    Show-ErrorAndExit $_.Exception.Message
}
