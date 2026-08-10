[CmdletBinding()]
param(
    [string]$Version = 'dev',
    [string]$Python = 'python',
    [string]$OutputRoot = ''
)

$ErrorActionPreference = 'Stop'
$RepositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (-not $OutputRoot) { $OutputRoot = Join-Path $RepositoryRoot 'artifacts' }
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
$BuildRoot = Join-Path $RepositoryRoot '.build'
$BinRoot = Join-Path $BuildRoot 'bin'
$WorkRoot = Join-Path $BuildRoot 'pyinstaller'
$SpecRoot = Join-Path $BuildRoot 'spec'
$PackageName = "RA3-Auto-Enhance-$Version"
$PackageRoot = Join-Path $OutputRoot $PackageName
$ZipPath = Join-Path $OutputRoot ($PackageName + '.zip')

function Assert-ChildPath([string]$Path, [string]$Parent) {
    $full = [IO.Path]::GetFullPath($Path)
    $parentFull = [IO.Path]::GetFullPath($Parent).TrimEnd('\') + '\'
    if (-not $full.StartsWith($parentFull, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path is outside the expected parent: $full"
    }
}

Assert-ChildPath $BuildRoot $RepositoryRoot
Assert-ChildPath $PackageRoot $OutputRoot
Assert-ChildPath $ZipPath $OutputRoot
foreach ($path in @($BuildRoot, $PackageRoot, $ZipPath, ($ZipPath + '.sha256'))) {
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Recurse -Force
    }
}
New-Item -ItemType Directory -Path $BinRoot,$WorkRoot,$SpecRoot,$PackageRoot,(Join-Path $PackageRoot 'bin'),(Join-Path $PackageRoot 'installer'),(Join-Path $PackageRoot 'licenses') -Force | Out-Null

$env:PYTHONPATH = Join-Path $RepositoryRoot 'src'
& $Python -m unittest discover -s (Join-Path $RepositoryRoot 'tests') -v
if ($LASTEXITCODE -ne 0) { throw 'Python tests failed.' }

$entries = [ordered]@{
    'RA3Borderless' = 'borderless.py'
    'RA3EdgeScroll' = 'edge_scroll.py'
    'RA3Ore100K' = 'ore100k.py'
    'RA3SteamOptions' = 'steam_options.py'
    'RA3AutoEnhance' = 'supervisor.py'
}
$common = @(
    '--noconfirm',
    '--clean',
    '--onefile',
    '--windowed',
    '--noupx',
    '--paths', (Join-Path $RepositoryRoot 'src'),
    '--distpath', $BinRoot,
    '--workpath', $WorkRoot,
    '--specpath', $SpecRoot
)
foreach ($entry in $entries.GetEnumerator()) {
    $script = Join-Path $RepositoryRoot (Join-Path 'src\ra3_auto' $entry.Value)
    & $Python -m PyInstaller @common --name $entry.Key $script
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed for $($entry.Key)." }
}

foreach ($name in $entries.Keys) {
    $exe = Join-Path $BinRoot ($name + '.exe')
    $process = Start-Process -FilePath $exe -ArgumentList '--self-test' -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "$name self-test failed with exit $($process.ExitCode)." }
    Copy-Item -LiteralPath $exe -Destination (Join-Path $PackageRoot 'bin')
}

$supervisorExe = Join-Path $BinRoot 'RA3AutoEnhance.exe'
$supervisor = Start-Process -FilePath $supervisorExe -ArgumentList @('--run-seconds','8') -WorkingDirectory $BinRoot -WindowStyle Hidden -PassThru
Wait-Process -Id $supervisor.Id -Timeout 20
Start-Sleep -Seconds 2
$leftovers = @(Get-CimInstance Win32_Process | Where-Object {
    $_.ExecutablePath -and $_.ExecutablePath.StartsWith(($BinRoot + '\'), [StringComparison]::OrdinalIgnoreCase)
})
if ($leftovers.Count -gt 0) {
    $leftovers | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    throw "Packaged supervisor left $($leftovers.Count) helper process(es) behind."
}

Copy-Item -LiteralPath (Join-Path $RepositoryRoot 'Install.cmd') -Destination $PackageRoot
Copy-Item -LiteralPath (Join-Path $RepositoryRoot 'Uninstall.cmd') -Destination $PackageRoot
Copy-Item -LiteralPath (Join-Path $RepositoryRoot 'installer\Install-RA3AutoEnhance.ps1') -Destination (Join-Path $PackageRoot 'installer')
Copy-Item -LiteralPath (Join-Path $RepositoryRoot 'installer\Uninstall-RA3AutoEnhance.ps1') -Destination (Join-Path $PackageRoot 'installer')
foreach ($document in @('README.md','LLM-GUIDE.md','LICENSE','THIRD-PARTY-NOTICES.md')) {
    Copy-Item -LiteralPath (Join-Path $RepositoryRoot $document) -Destination $PackageRoot
}
$pythonBase = (& $Python -c "import sys; print(sys.base_prefix)").Trim()
$pyInstallerLicense = (& $Python -c "import importlib.metadata as m, pathlib; d=m.distribution('pyinstaller'); print(next(pathlib.Path(d.locate_file(f)) for f in d.files if f.name == 'COPYING.txt'))").Trim()
Copy-Item -LiteralPath (Join-Path $pythonBase 'LICENSE.txt') -Destination (Join-Path $PackageRoot 'licenses\PYTHON-LICENSE.txt')
Copy-Item -LiteralPath $pyInstallerLicense -Destination (Join-Path $PackageRoot 'licenses\PYINSTALLER-LICENSE.txt')
Set-Content -LiteralPath (Join-Path $PackageRoot 'VERSION.txt') -Value ($Version + "`n") -Encoding ascii

& (Join-Path $RepositoryRoot 'tools\Test-Package.ps1') -PackageRoot $PackageRoot
Compress-Archive -LiteralPath $PackageRoot -DestinationPath $ZipPath -CompressionLevel Optimal
$hash = (Get-FileHash -LiteralPath $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath ($ZipPath + '.sha256') -Value ("$hash  $([IO.Path]::GetFileName($ZipPath))`n") -Encoding ascii

Write-Host "Release package: $ZipPath" -ForegroundColor Green
Write-Host "SHA256: $hash"
