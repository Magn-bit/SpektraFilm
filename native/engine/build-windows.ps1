param([string]$Distribution = 'Ubuntu-24.04')
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'Use PowerShell 7 (pwsh).' }
$nativeScript = (Join-Path $PSScriptRoot 'build-windows.sh').Replace('\', '/')
$wslScript = (& wsl.exe -d $Distribution -- wslpath -u $nativeScript).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Unable to resolve the native build path in WSL' }
& wsl.exe -d $Distribution -- bash $wslScript
if ($LASTEXITCODE -ne 0) { throw "Native spectral build failed ($LASTEXITCODE)" }
