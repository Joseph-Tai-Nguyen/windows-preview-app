<#
.SYNOPSIS
    Build the offline Windows installer: release\WinPreview-<version>-setup-x64.exe
.DESCRIPTION
    1. Runs scripts\build.ps1 (PyInstaller -> dist\WinPreview\), unless -SkipAppBuild.
    2. Compiles installer\winpreview.iss with Inno Setup 6 (ISCC.exe).
    Install Inno Setup once with:  winget install --id JRSoftware.InnoSetup -e
#>
param([switch]$SkipAppBuild)

# Native tools log to stderr; failures are detected via $LASTEXITCODE instead.
$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not $SkipAppBuild) {
    & (Join-Path $PSScriptRoot "build.ps1")
}
if (-not (Test-Path "dist\WinPreview\WinPreview.exe")) {
    throw "dist\WinPreview\WinPreview.exe not found. Run scripts\build.ps1 first."
}

$candidates = @(
    (Get-Command iscc.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path $_) }
$iscc = $candidates | Select-Object -First 1
if (-not $iscc) {
    throw "Inno Setup 6 not found. Install it with: winget install --id JRSoftware.InnoSetup -e"
}

$version = (& .venv\Scripts\python -c "import winpreview; print(winpreview.__version__)").Trim()
& $iscc "/DAppVersion=$version" "installer\winpreview.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed." }

$setup = Get-Item "release\WinPreview-$version-setup-x64.exe"
Write-Host ("Installer: {0} ({1:N0} MB)" -f $setup.FullName, ($setup.Length / 1MB)) -ForegroundColor Green
