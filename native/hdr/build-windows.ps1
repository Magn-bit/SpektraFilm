param([string]$Distribution = 'Ubuntu-24.04')
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'Use PowerShell 7 (pwsh).' }
$hdrScript = (Join-Path $PSScriptRoot 'build-windows.sh').Replace('\', '/')
$hdrWslScript = (& wsl.exe -d $Distribution -- wslpath -u $hdrScript).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Unable to resolve HDR build path in WSL' }
& wsl.exe -d $Distribution -- bash $hdrWslScript
if ($LASTEXITCODE -ne 0) { throw "HDR codec build failed ($LASTEXITCODE)" }
