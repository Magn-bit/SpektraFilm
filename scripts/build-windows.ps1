param(
    [string]$Destination = 'dist',
    [string]$WorkDirectory = 'build/windows',
    [string]$Python = '.venv/Scripts/python.exe'
)
$ErrorActionPreference='Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'Use PowerShell 7 (pwsh).' }
Set-Location (Split-Path $PSScriptRoot -Parent)
$destinationPath=[IO.Path]::GetFullPath($Destination,$PWD.Path)
$workPath=[IO.Path]::GetFullPath($WorkDirectory,$PWD.Path)
$pythonCommand=(Resolve-Path -LiteralPath $Python).Path
if (-not (Test-Path -LiteralPath 'native/engine/runtime/spektrafilm_engine.dll')) {
    throw 'Build the native spectral engine first: ./native/engine/build-windows.ps1'
}
foreach ($requiredRuntime in @('native/library/runtime/spklib-host.exe','native/color/runtime/spektrafilm_lcms2.dll','native/hdr/runtime/spektrafilm_hdr.dll')) {
    if (-not (Test-Path -LiteralPath $requiredRuntime)) { throw "Build the required native runtime first: $requiredRuntime" }
}
if (-not (Test-Path -LiteralPath 'native/metadata/runtime/exiftool-13.61_64/exiftool.exe')) {
    & $pythonCommand -X utf8 scripts/install_metadata_runtime.py
    if ($LASTEXITCODE -ne 0) { throw 'ExifTool runtime installation failed.' }
}
& $pythonCommand -c 'import PyInstaller' 2>$null
if ($LASTEXITCODE -ne 0) {
    & $pythonCommand -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller installation failed.' }
}
# wgpu's installed wheel registers its own PyInstaller hook. The hook keeps
# combined_header.h and the matching wgpu_native DLL under wgpu/resources.
& $pythonCommand -c 'from importlib.metadata import version; from importlib.resources import files; assert version("wgpu") == "0.33.0"; resources=files("wgpu.resources"); assert (resources / "combined_header.h").is_file(); assert (resources / "wgpu_native-release.dll").is_file()'
if ($LASTEXITCODE -ne 0) { throw 'Install requirements.txt: packaging needs the wgpu 0.33.0 Windows wheel with matching headers and DLL.' }
$originalBuildPath=$env:PATH
$originalPythonPath=$env:PYTHONPATH
try {
    # Do not resolve Qt's system ICU against unrelated Poppler/libheif DLLs
    # supplied by a host application or another development tool on PATH.
    $env:PATH="$env:SystemRoot\System32;$env:SystemRoot;$(Split-Path $pythonCommand -Parent)"
    $env:PYTHONPATH=Join-Path $PWD 'vendor'
    $rootPath=$PWD.Path
    & $pythonCommand -X utf8 -m PyInstaller --clean --noconfirm --workpath $workPath --distpath $destinationPath "$rootPath/scripts/windows.spec"
    if ($LASTEXITCODE -ne 0) { throw 'Windows packaging failed.' }
} finally {
    $env:PATH=$originalBuildPath
    $env:PYTHONPATH=$originalPythonPath
}
Write-Host "Application: $Destination/SpektraFilm/SpektraFilm.exe"
