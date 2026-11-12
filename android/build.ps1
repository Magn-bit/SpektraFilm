param([switch]$Release, [string]$GradlePath, [string]$SdkPath)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'Use PowerShell 7 (pwsh) to build.' }
$devRoot = Join-Path $env:LOCALAPPDATA 'SpektraFilmDev'
$gradle = if ($GradlePath) { $GradlePath } else { Join-Path $devRoot 'gradle-8.13/bin/gradle.bat' }
if (-not (Test-Path -LiteralPath $gradle)) { throw 'Provide -GradlePath or install Gradle 8.13 under %LOCALAPPDATA%/SpektraFilmDev.' }
$env:ANDROID_HOME = if ($SdkPath) { $SdkPath } elseif ($env:ANDROID_HOME) { $env:ANDROID_HOME } else { Join-Path $devRoot 'android-sdk' }
if (-not (Test-Path -LiteralPath (Join-Path $env:ANDROID_HOME 'platforms/android-35/android.jar'))) { throw 'Install Android SDK 35 or provide -SdkPath.' }
$sdkPath = $env:ANDROID_HOME.Replace('\','/')
[System.IO.File]::WriteAllText((Join-Path $PSScriptRoot 'local.properties'), "sdk.dir=$sdkPath`n")
Push-Location $PSScriptRoot
try {
    $target = if ($Release) { 'assembleRelease' } else { 'assembleDebug' }
    & $gradle --no-daemon $target
    if ($LASTEXITCODE -ne 0) { throw "Gradle failed: $LASTEXITCODE" }
} finally { Pop-Location }
