$ErrorActionPreference='Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'Use PowerShell 7 (pwsh).' }
Set-Location $PSScriptRoot
if (-not (Test-Path '.venv/Scripts/python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 or newer is required to create the environment.' }
}
& .venv/Scripts/python.exe -X utf8 scripts/check_dependencies.py
if ($LASTEXITCODE -ne 0) {
    & .venv/Scripts/python.exe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
}
if (-not (Test-Path 'assets/luts/manifest.json')) {
    & .venv/Scripts/python.exe scripts/build_luts.py
    if ($LASTEXITCODE -ne 0) { throw 'Film LUT creation failed.' }
}
& .venv/Scripts/python.exe -m desktop.main @args
