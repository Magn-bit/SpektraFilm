#requires -Version 7.0
<#
.SYNOPSIS
Lists disposable project files; -Apply removes them after checking every path.
.EXAMPLE
pwsh -File scripts/clean-workspace.ps1
.EXAMPLE
pwsh -File scripts/clean-workspace.ps1 -Apply
.EXAMPLE
pwsh -File scripts/clean-workspace.ps1 -Apply -KeepDevEnvironment
#>
[CmdletBinding(SupportsShouldProcess)]
param([switch]$Apply, [switch]$KeepDevEnvironment)

$ErrorActionPreference = 'Stop'
$workspaceRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot)).TrimEnd('\', '/')
$workspacePrefix = $workspaceRoot + [IO.Path]::DirectorySeparatorChar
foreach ($required in @('desktop/controller.py', 'android/app/src', 'release/manifest.json')) {
    if (!(Test-Path -LiteralPath (Join-Path $workspaceRoot $required))) {
        throw "Project identity check failed: $required"
    }
}

$manifest = Get-Content -LiteralPath (Join-Path $workspaceRoot 'release/manifest.json') -Raw | ConvertFrom-Json
$requiredRelease = @($manifest.windows.executable, $manifest.windows.console,
    $manifest.android.apk, $manifest.android.source, $manifest.source.archive)
foreach ($file in $manifest.distribution.windows.files) { $requiredRelease += "Windows/$file" }
foreach ($relative in $requiredRelease) {
    if (!(Test-Path -LiteralPath (Join-Path $workspaceRoot "release/$relative") -PathType Leaf)) {
        throw "Keep the complete current release before cleaning: $relative"
    }
}

$relativeTargets = @('.tmp-smoke', '.tools', 'build', 'dist', 'dist-frame-fix', 'output',
    'android/.gradle', 'android/.kotlin', 'android/build', 'android/app/build', 'android/app/.cxx')
if (!$KeepDevEnvironment) { $relativeTargets += '.venv' }
$relativeTargets += @(Get-ChildItem -LiteralPath $workspaceRoot -File -Force -Filter '.tmp-*.png' |
    ForEach-Object { $_.Name })
# Python caches inside actual source trees, never inside the retained release.
foreach ($tree in @('desktop', 'shared', 'tests', 'scripts', 'vendor', 'native', 'android/tools')) {
    $relativeTargets += @(Get-ChildItem -LiteralPath (Join-Path $workspaceRoot $tree) -Directory -Recurse -Force -Filter '__pycache__' |
        ForEach-Object { [IO.Path]::GetRelativePath($workspaceRoot, $_.FullName) })
}

$gitRoot = $workspaceRoot.Replace('\', '/')
$tracked = @(& git -c "safe.directory=$gitRoot" -C $workspaceRoot ls-files)
if ($LASTEXITCODE -ne 0) { throw 'Cannot check tracked source files; cleanup cancelled.' }
$targets = foreach ($relative in ($relativeTargets | Sort-Object -Unique)) {
    $absolute = [IO.Path]::GetFullPath((Join-Path $workspaceRoot $relative))
    if (!$absolute.StartsWith($workspacePrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Target outside project: $absolute"
    }
    if (!(Test-Path -LiteralPath $absolute)) { continue }
    $item = Get-Item -LiteralPath $absolute -Force
    if ($item.Attributes.HasFlag([IO.FileAttributes]::ReparsePoint)) {
        throw "Reparse point requires separate review: $absolute"
    }
    $gitRelative = [IO.Path]::GetRelativePath($workspaceRoot, $absolute).Replace('\', '/')
    if ($tracked.Where({ $_ -eq $gitRelative -or $_.StartsWith($gitRelative + '/', [StringComparison]::OrdinalIgnoreCase) }).Count) {
        throw "Target contains tracked source files: $gitRelative"
    }
    $bytes = if ($item.PSIsContainer) {
        (Get-ChildItem -LiteralPath $absolute -Recurse -Force -File | Measure-Object -Property Length -Sum).Sum
    } else { $item.Length }
    [pscustomobject]@{ Path = $absolute; MiB = [math]::Round($bytes / 1MB, 1) }
}
$targets | Format-Table -AutoSize
if (!$Apply) {
    Write-Output 'Preview only. Use -Apply to remove the listed generated files.'
    return
}
$active = @(Get-CimInstance Win32_Process | Where-Object {
    $_.ExecutablePath -and $_.ExecutablePath.StartsWith($workspacePrefix, [StringComparison]::OrdinalIgnoreCase) -and
    $_.Name -match '^(SpektraFilm(CLI)?|python(w)?)\.exe$'
})
if ($active.Count) { throw 'Close project application/Python processes before cleaning.' }
foreach ($target in $targets) {
    if ($PSCmdlet.ShouldProcess($target.Path, 'Remove disposable project files')) {
        Remove-Item -LiteralPath $target.Path -Recurse -Force
    }
}
