#Requires -Version 7
<#
.SYNOPSIS
  Local build helper for the PlexMuxy Windows installer.

.DESCRIPTION
  Reads the single-source version from plexmuxy/VERSION, generates a PyInstaller
  version-info resource, runs both PyInstaller specs (CLI + GUI), then builds the
  Inno Setup installer. Use this for local verification before the CI release
  workflow takes over.

  The version is never hard-coded here: it is taken verbatim from plexmuxy/VERSION,
  which is also what plexmuxy.__version__ and the published wheel read.

.EXAMPLE
  pwsh scripts/build_installer.ps1
#>
[CmdletBinding()]
param(
  [switch]$SkipCli,
  [switch]$SkipInstaller
)

$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..')
Set-Location $root

# 1. Single-source version, identical to plexmuxy.__version__.
$version = (Get-Content plexmuxy/VERSION -Encoding utf8).Trim()
if (-not $version) { throw 'plexmuxy/VERSION is empty.' }
Write-Host "Building PlexMuxy $version" -ForegroundColor Cyan

if ($version -match '^(\d+)\.(\d+)\.(\d+)') {
  $filevers = "$([int]$Matches[1]), $([int]$Matches[2]), $([int]$Matches[3]), 0"
  $prodvers = $filevers
} else {
  throw "Cannot parse version '$version' as MAJOR.MINOR.PATCH."
}

function New-VersionInfo {
  param([string]$OriginalName)
  @"
# UTF-8
#
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($filevers),
    prodvers=($prodvers),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'PlexMuxy contributors'),
         StringStruct(u'FileDescription', u'PlexMuxy'),
         StringStruct(u'FileVersion', u'$version'),
         StringStruct(u'InternalName', u'plexmuxy'),
         StringStruct(u'LegalCopyright', u'MIT License'),
         StringStruct(u'OriginalFilename', u'$OriginalName'),
         StringStruct(u'ProductName', u'PlexMuxy'),
         StringStruct(u'ProductVersion', u'$version')])
    ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"@
}

# 2. PyInstaller builds. Prefer uv when available so optional build/gui deps resolve.
$hasUv = [bool](Get-Command uv -ErrorAction SilentlyContinue)
function Invoke-PyInstaller($spec) {
  if ($script:hasUv) {
    uv run --extra build --extra gui -- python -m PyInstaller --clean --noconfirm $spec
  } else {
    python -m PyInstaller --clean --noconfirm $spec
  }
}

if (-not $SkipCli) {
  New-VersionInfo -OriginalName 'plexmuxy.exe' | Out-File -Encoding utf8 packaging/version_info.txt
  Invoke-PyInstaller plexmuxy-cli.spec
}
New-VersionInfo -OriginalName 'plexmuxy-gui.exe' | Out-File -Encoding utf8 packaging/version_info.txt
Invoke-PyInstaller plexmuxy-gui.spec

# 3. Inno Setup installer. The version is forwarded so the .iss never hard-codes it.
if (-not $SkipInstaller) {
  $iscc = Get-Command iscc -ErrorAction SilentlyContinue
  if (-not $iscc) {
    throw "Inno Setup (iscc) not found. Install it (e.g. 'choco install innosetup') and retry."
  }
  & $iscc.Path "/DMyAppVersion=$version" packaging/plexmuxy.iss
  if ($LASTEXITCODE -ne 0) { throw "iscc failed with exit code $LASTEXITCODE." }
  Write-Host "Installer: dist/plexmuxy-$version-windows-x64-setup.exe" -ForegroundColor Green
}
