<#
.SYNOPSIS
    Quality gate: ruff lint, ruff format check, pytest. Exits non-zero on failure.
#>
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$failed = @()

Write-Host "== ruff check ==" -ForegroundColor Cyan
& .venv\Scripts\ruff check src tests
if ($LASTEXITCODE -ne 0) { $failed += "ruff check" }

Write-Host "== ruff format --check ==" -ForegroundColor Cyan
& .venv\Scripts\ruff format --check src tests
if ($LASTEXITCODE -ne 0) { $failed += "ruff format" }

Write-Host "== pytest ==" -ForegroundColor Cyan
& .venv\Scripts\python -m pytest -q
if ($LASTEXITCODE -ne 0) { $failed += "pytest" }

if ($failed.Count -gt 0) {
    Write-Host ("FAILED: " + ($failed -join ", ")) -ForegroundColor Red
    exit 1
}
Write-Host "All checks passed." -ForegroundColor Green
