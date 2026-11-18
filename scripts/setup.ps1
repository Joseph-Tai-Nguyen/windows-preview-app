<#
.SYNOPSIS
    Create .venv and install WinPreview in editable mode with dev tools.
.PARAMETER Python
    Python launcher selector, e.g. "3.12". Defaults to the newest installed.
#>
param([string]$Python = "")

# Native tools log to stderr; failures are detected via $LASTEXITCODE instead.
$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    $launcherArgs = @()
    if ($Python) { $launcherArgs += "-$Python" }
    Write-Host "Creating virtual environment (.venv)..."
    & py @launcherArgs -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Failed to create .venv. Is Python 3.11+ installed (py launcher)?" }
}

& .venv\Scripts\python -m pip install --upgrade pip
& .venv\Scripts\python -m pip install -e ".[dev]"
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }

Write-Host ""
Write-Host "Ready. Try: ./scripts/run.ps1   or   ./scripts/check.ps1"
