<#
.SYNOPSIS
    Build a distributable folder dist\WinPreview\ with PyInstaller.
    The exe gets the app icon and Windows version info (Properties > Details).
#>
# Native tools log to stderr; failures are detected via $LASTEXITCODE instead.
$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..")

& .venv\Scripts\python -m pip install -e ".[build]"
if ($LASTEXITCODE -ne 0) { throw "Could not install build dependencies." }

$version = (& .venv\Scripts\python -c "import winpreview; print(winpreview.__version__)").Trim()
$parts = @($version.Split(".") + @("0", "0", "0", "0"))[0..3] -join ", "
$icon = "src\winpreview\resources\icons\winpreview.ico"

New-Item -ItemType Directory -Force build | Out-Null
$versionFile = "build\version_info.txt"
@"
VSVersionInfo(
  ffi=FixedFileInfo(filevers=($parts), prodvers=($parts), mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'WinPreview contributors'),
      StringStruct('FileDescription', 'WinPreview - PDF page organizer'),
      StringStruct('FileVersion', '$version'),
      StringStruct('InternalName', 'WinPreview'),
      StringStruct('LegalCopyright', 'GPL-3.0-or-later'),
      StringStruct('OriginalFilename', 'WinPreview.exe'),
      StringStruct('ProductName', 'WinPreview'),
      StringStruct('ProductVersion', '$version')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"@ | Set-Content -Encoding utf8 $versionFile

& .venv\Scripts\pyinstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name WinPreview `
    --icon $icon `
    --version-file $versionFile `
    --paths src `
    --collect-submodules winpreview `
    --add-data "src\winpreview\resources\icons;winpreview\resources\icons" `
    src\winpreview\__main__.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

# OpenCV (needed by pdf2docx for Word export) ships a 40 MB FFmpeg DLL that it only
# loads for video I/O, which the app never does.
Remove-Item "dist\WinPreview\_internal\cv2\opencv_videoio_ffmpeg*.dll" -ErrorAction SilentlyContinue

Write-Host "Built dist\WinPreview\WinPreview.exe (v$version)" -ForegroundColor Green
