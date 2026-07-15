[CmdletBinding()]
param(
    [string]$Marker = "not integration",
    [switch]$Coverage
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$runRoot = Join-Path $root ".pytest-tmp\$PID"
$systemTemp = Join-Path $runRoot "system"
$pytestTemp = Join-Path $runRoot "pytest"
$cacheDir = Join-Path $runRoot "cache"
New-Item -ItemType Directory -Force $systemTemp, $pytestTemp, $cacheDir | Out-Null
$env:TEMP = (Resolve-Path -LiteralPath $systemTemp).Path
$env:TMP = $env:TEMP
$arguments = @("run", "--extra", "dev", "pytest", "-m", $Marker, "--basetemp", $pytestTemp, "-o", "cache_dir=$cacheDir")
if ($Coverage) {
    $arguments += @("--cov", "--cov-report=term", "--cov-fail-under=75")
}
& uv @arguments
exit $LASTEXITCODE
