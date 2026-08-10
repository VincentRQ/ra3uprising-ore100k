[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$PackageRoot
)

$ErrorActionPreference = 'Stop'
$PackageRoot = [IO.Path]::GetFullPath($PackageRoot)
$required = @(
    'Install.cmd',
    'Uninstall.cmd',
    'README.md',
    'LLM-GUIDE.md',
    'LICENSE',
    'THIRD-PARTY-NOTICES.md',
    'licenses\PYTHON-LICENSE.txt',
    'licenses\PYINSTALLER-LICENSE.txt',
    'installer\Install-RA3AutoEnhance.ps1',
    'installer\Uninstall-RA3AutoEnhance.ps1',
    'bin\RA3AutoEnhance.exe',
    'bin\RA3Borderless.exe',
    'bin\RA3EdgeScroll.exe',
    'bin\RA3Ore100K.exe',
    'bin\RA3SteamOptions.exe'
)
foreach ($relative in $required) {
    if (-not (Test-Path -LiteralPath (Join-Path $PackageRoot $relative))) {
        throw "Package file is missing: $relative"
    }
}

$testRoot = Join-Path ([IO.Path]::GetTempPath()) ("RA3AutoEnhance-InstallTest-" + [Guid]::NewGuid().ToString('N'))
try {
    & (Join-Path $PackageRoot 'installer\Install-RA3AutoEnhance.ps1') `
        -InstallRoot $testRoot -SkipTask -NoPrompt -SkipShortcut -SkipSteamOptions -AllowCustomRoot
    foreach ($name in @('RA3AutoEnhance.exe','RA3Borderless.exe','RA3EdgeScroll.exe','RA3Ore100K.exe','RA3SteamOptions.exe')) {
        if (-not (Test-Path -LiteralPath (Join-Path $testRoot $name))) {
            throw "Installer did not copy $name"
        }
    }
    foreach ($license in @('licenses\PYTHON-LICENSE.txt','licenses\PYINSTALLER-LICENSE.txt')) {
        if (-not (Test-Path -LiteralPath (Join-Path $testRoot $license))) {
            throw "Installer did not copy $license"
        }
    }
    & (Join-Path $PackageRoot 'installer\Uninstall-RA3AutoEnhance.ps1') `
        -InstallRoot $testRoot -SkipTask -NoPrompt -KeepSteamOptions -SkipShortcut -AllowCustomRoot
    if (Test-Path -LiteralPath $testRoot) {
        throw "Uninstaller left the staging directory behind: $testRoot"
    }
} finally {
    if (Test-Path -LiteralPath $testRoot) {
        $resolved = [IO.Path]::GetFullPath($testRoot)
        $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
        if ($resolved.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase) -and (Split-Path $resolved -Leaf).StartsWith('RA3AutoEnhance-InstallTest-')) {
            Remove-Item -LiteralPath $resolved -Recurse -Force
        }
    }
}
Write-Host 'Package install/uninstall staging test passed.' -ForegroundColor Green
