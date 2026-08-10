[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'RA3AutoEnhance'),
    [string]$TaskName = 'RA3 Auto Enhance',
    [switch]$SkipTask,
    [switch]$NoPrompt,
    [switch]$CloseSteam,
    [switch]$KeepSteamOptions,
    [switch]$SkipShortcut,
    [switch]$AllowCustomRoot
)

$ErrorActionPreference = 'Stop'

function Get-FullPath([string]$Path) {
    return [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($Path))
}

function Assert-SafeInstallRoot([string]$Path) {
    $full = Get-FullPath $Path
    if ($full -eq [IO.Path]::GetPathRoot($full)) {
        throw "Refusing to remove a drive root: $full"
    }
    $defaultRoot = Get-FullPath (Join-Path $env:LOCALAPPDATA 'RA3AutoEnhance')
    if (-not $AllowCustomRoot -and $full -ne $defaultRoot) {
        throw "Custom InstallRoot requires -AllowCustomRoot: $full"
    }
    $marker = Join-Path $full '.ra3-auto-enhance-install.json'
    if (-not (Test-Path -LiteralPath $marker)) {
        throw "Install marker is missing; refusing recursive removal: $full"
    }
    return $full
}

function Wait-ForSteamExit([int]$TimeoutSeconds = 45) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if (-not (Get-Process -Name steam -ErrorAction SilentlyContinue)) { return $true }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)
    return $false
}

$InstallRoot = Assert-SafeInstallRoot $InstallRoot
Write-Host "Uninstalling RA3 Auto Enhance from $InstallRoot"

if (-not $SkipTask) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
}

$prefix = $InstallRoot.TrimEnd('\') + '\'
$names = @('RA3AutoEnhance.exe','RA3Borderless.exe','RA3EdgeScroll.exe','RA3Ore100K.exe','RA3SteamOptions.exe')
Get-CimInstance Win32_Process | Where-Object {
    $_.Name -in $names -and $_.ExecutablePath -and $_.ExecutablePath.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)
} | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 1

if (-not $KeepSteamOptions) {
    $steamRunning = [bool](Get-Process -Name steam -ErrorAction SilentlyContinue)
    $closeNow = $CloseSteam
    if ($steamRunning -and -not $CloseSteam -and -not $NoPrompt) {
        $answer = Read-Host 'Close Steam now so the installer-owned -win options can be removed? [Y/n]'
        $closeNow = [string]::IsNullOrWhiteSpace($answer) -or $answer.Trim().StartsWith('y', [StringComparison]::OrdinalIgnoreCase)
    }
    if ($steamRunning -and $closeNow) {
        $steamPath = (Get-ItemProperty -LiteralPath 'HKCU:\Software\Valve\Steam').SteamPath
        $steamExe = Join-Path $steamPath 'steam.exe'
        Start-Process -FilePath $steamExe -ArgumentList '-shutdown' -WindowStyle Hidden
        if (-not (Wait-ForSteamExit)) { throw 'Steam did not exit within 45 seconds.' }
        $steamRunning = $false
    }
    if (-not $steamRunning) {
        $optionsExe = Join-Path $InstallRoot 'RA3SteamOptions.exe'
        if (Test-Path -LiteralPath $optionsExe) {
            $process = Start-Process -FilePath $optionsExe -ArgumentList '--remove-owned' -WindowStyle Hidden -PassThru
            $process.WaitForExit()
        }
    } else {
        Write-Warning 'Steam stayed open, so its -win options were left unchanged.'
    }
}

if (-not $SkipShortcut) {
    $shortcutPath = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Uninstall RA3 Auto Enhance.lnk'
    if (Test-Path -LiteralPath $shortcutPath) {
        Remove-Item -LiteralPath $shortcutPath -Force
    }
}

Remove-Item -LiteralPath $InstallRoot -Recurse -Force
Write-Host 'RA3 Auto Enhance was removed.' -ForegroundColor Green
