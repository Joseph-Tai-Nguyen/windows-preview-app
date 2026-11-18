<#
.SYNOPSIS
    Launch WinPreview, optionally opening a PDF.
.EXAMPLE
    ./scripts/run.ps1 C:\Docs\contract.pdf
#>
param([string]$File = "")

$ErrorActionPreference = "Stop"
$root = Join-Path $PSScriptRoot ".."
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "No .venv found. Run ./scripts/setup.ps1 first." }

if ($File) {
    & $python -m winpreview (Resolve-Path $File)
} else {
    & $python -m winpreview
}
