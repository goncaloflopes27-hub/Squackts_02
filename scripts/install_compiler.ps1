[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$pin = Get-Content (Join-Path $root 'packaging\innosetup.json') -Raw | ConvertFrom-Json
$installer = Join-Path $env:RUNNER_TEMP "innosetup-$($pin.version).exe"
Invoke-WebRequest -Uri $pin.url -OutFile $installer
$digest = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
if ($digest -ne $pin.sha256) { throw 'O instalador do compilador nao corresponde ao SHA-256 fixado.' }
$destination = Join-Path $env:RUNNER_TEMP "InnoSetup-$($pin.version)"
$process = Start-Process -FilePath $installer -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/CURRENTUSER', "/DIR=`"$destination`"") -Wait -PassThru
if ($process.ExitCode -ne 0) { throw 'Falha ao instalar o compilador fixado.' }
$compiler = Join-Path $destination 'ISCC.exe'
if (-not (Test-Path -LiteralPath $compiler)) { throw 'Compilador ausente.' }
"SQUACKTS_ISCC=$compiler" | Out-File -FilePath $env:GITHUB_ENV -Encoding utf8 -Append
