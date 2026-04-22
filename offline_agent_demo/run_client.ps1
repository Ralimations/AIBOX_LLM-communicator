$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$clientPath = Join-Path $scriptDir "client.py"

if (-not (Test-Path -LiteralPath $clientPath)) {
    throw "Client script not found: $clientPath"
}

function Start-ClientWith {
    param(
        [string]$Exe,
        [string[]]$Arguments
    )

    & $Exe @Arguments
    exit $LASTEXITCODE
}

try {
    $pythonCmd = Get-Command python -ErrorAction Stop
    Start-ClientWith -Exe $pythonCmd.Source -Arguments @($clientPath)
}
catch {
}

try {
    $pyCmd = Get-Command py -ErrorAction Stop
    Start-ClientWith -Exe $pyCmd.Source -Arguments @("-3", $clientPath)
}
catch {
}

throw @"
No usable Python launcher was found.

Install Python 3, or run the client manually with one of these:

  python `"$clientPath`"
  py -3 `"$clientPath`"
"@
