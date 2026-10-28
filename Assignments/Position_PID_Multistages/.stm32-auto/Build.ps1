param([string]$ProjectPath, [switch]$Check)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
try {
    if ([string]::IsNullOrWhiteSpace($ProjectPath)) { $ProjectPath = Split-Path $PSScriptRoot -Parent }
    $root = (Resolve-Path -LiteralPath $ProjectPath).Path
    $python = Join-Path $env:USERPROFILE '.eide/bin/python36/python3.exe'
    if (!(Test-Path -LiteralPath $python)) { throw 'EIDE bundled Python missing. Initialize EIDE first.' }
    $action = if ($Check) {'check'} else {'build'}
    & $python (Join-Path $PSScriptRoot 'project.py') $action $root
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} catch { Write-Error $_ -ErrorAction Continue; exit 1 }
