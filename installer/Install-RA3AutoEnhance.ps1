[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'RA3AutoEnhance'),
    [string]$TaskName = 'RA3 Auto Enhance',
    [switch]$SkipTask,
    [switch]$NoPrompt,
    [switch]$RestartSteam,
    [switch]$SkipShortcut,
    [switch]$SkipSteamOptions,
    [switch]$AllowCustomRoot
)

$ErrorActionPreference = 'Stop'
$RequiredExecutables = @(
    'RA3AutoEnhance.exe',
    'RA3Borderless.exe',
    'RA3EdgeScroll.exe',
    'RA3Ore100K.exe',
    'RA3SteamOptions.exe'
)

function Get-FullPath([string]$Path) {
    return [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($Path))
}

function Assert-SafeInstallRoot([string]$Path) {
    $full = Get-FullPath $Path
    if ($full -eq [IO.Path]::GetPathRoot($full)) {
        throw "Refusing to use a drive root as InstallRoot: $full"
    }
    $defaultRoot = Get-FullPath (Join-Path $env:LOCALAPPDATA 'RA3AutoEnhance')
    if (-not $AllowCustomRoot -and $full -ne $defaultRoot) {
        throw "Custom InstallRoot requires -AllowCustomRoot: $full"
    }
    return $full
}

function Stop-InstalledProcesses([string]$Root) {
    $prefix = $Root.TrimEnd('\') + '\'
    $names = @('RA3AutoEnhance.exe','RA3Borderless.exe','RA3EdgeScroll.exe','RA3Ore100K.exe','RA3SteamOptions.exe')
    Get-CimInstance Win32_Process | Where-Object {
        $_.Name -in $names -and $_.ExecutablePath -and $_.ExecutablePath.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)
    } | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

function Wait-ForSteamExit([int]$TimeoutSeconds = 45) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if (-not (Get-Process -Name steam -ErrorAction SilentlyContinue)) { return $true }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)
    return $false
}

function Get-SteamExecutable {
    try {
        $steamPath = (Get-ItemProperty -LiteralPath 'HKCU:\Software\Valve\Steam').SteamPath
        if ($steamPath) {
            $candidate = Join-Path $steamPath 'steam.exe'
            if (Test-Path -LiteralPath $candidate) { return $candidate }
        }
    } catch {}
    return $null
}

function Set-SteamOptions([string]$Root) {
    $optionsExe = Join-Path $Root 'RA3SteamOptions.exe'
    $process = Start-Process -FilePath $optionsExe -ArgumentList '--once' -WindowStyle Hidden -PassThru
    $process.WaitForExit()
    if ($process.ExitCode -notin @(0, 2)) {
        Write-Warning "Steam launch options were not updated (exit $($process.ExitCode)). The watcher will retry after Steam exits."
    }
}

if ($env:OS -ne 'Windows_NT') { throw 'RA3 Auto Enhance supports Windows only.' }
$InstallRoot = Assert-SafeInstallRoot $InstallRoot
$PackageRoot = Get-FullPath (Join-Path $PSScriptRoot '..')
$BinRoot = Join-Path $PackageRoot 'bin'

foreach ($name in $RequiredExecutables) {
    $source = Join-Path $BinRoot $name
    if (-not (Test-Path -LiteralPath $source)) {
        throw "Missing packaged executable: $source. Download the release ZIP, not the source archive."
    }
}

Write-Host "Installing RA3 Auto Enhance to $InstallRoot"
if (-not $SkipTask) {
    $existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existingTask) {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }
}
Stop-InstalledProcesses $InstallRoot

New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
foreach ($name in $RequiredExecutables) {
    Copy-Item -LiteralPath (Join-Path $BinRoot $name) -Destination (Join-Path $InstallRoot $name) -Force
}
New-Item -ItemType Directory -Path (Join-Path $InstallRoot 'installer') -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $PackageRoot 'installer\Uninstall-RA3AutoEnhance.ps1') -Destination (Join-Path $InstallRoot 'installer\Uninstall-RA3AutoEnhance.ps1') -Force
Copy-Item -LiteralPath (Join-Path $PackageRoot 'Uninstall.cmd') -Destination (Join-Path $InstallRoot 'Uninstall.cmd') -Force
foreach ($document in @('README.md','LLM-GUIDE.md','LICENSE','THIRD-PARTY-NOTICES.md')) {
    Copy-Item -LiteralPath (Join-Path $PackageRoot $document) -Destination (Join-Path $InstallRoot $document) -Force
}
Copy-Item -LiteralPath (Join-Path $PackageRoot 'licenses') -Destination (Join-Path $InstallRoot 'licenses') -Recurse -Force

$marker = @{
    product = 'RA3 Auto Enhance'
    installed_at = (Get-Date).ToString('o')
    install_root = $InstallRoot
} | ConvertTo-Json
Set-Content -LiteralPath (Join-Path $InstallRoot '.ra3-auto-enhance-install.json') -Value $marker -Encoding utf8

if (-not $SkipTask) {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $action = New-ScheduledTaskAction -Execute (Join-Path $InstallRoot 'RA3AutoEnhance.exe') -WorkingDirectory $InstallRoot
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
    $principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
    Start-ScheduledTask -TaskName $TaskName
    Start-Sleep -Seconds 3
    $task = Get-ScheduledTask -TaskName $TaskName
    if ($task.State -ne 'Running') { throw "Scheduled task did not remain running (state: $($task.State))." }
}

if (-not $SkipSteamOptions) {
    $steamWasRunning = [bool](Get-Process -Name steam -ErrorAction SilentlyContinue)
    $restartNow = $RestartSteam
    if ($steamWasRunning -and -not $RestartSteam -and -not $NoPrompt) {
        $answer = Read-Host 'Steam must restart once to load -win for both games. Restart Steam now? [Y/n]'
        $restartNow = [string]::IsNullOrWhiteSpace($answer) -or $answer.Trim().StartsWith('y', [StringComparison]::OrdinalIgnoreCase)
    }

    if ($steamWasRunning -and $restartNow) {
        $steamExe = Get-SteamExecutable
        if (-not $steamExe) { throw 'Steam executable was not found in the current-user registry.' }
        Start-Process -FilePath $steamExe -ArgumentList '-shutdown' -WindowStyle Hidden
        if (-not (Wait-ForSteamExit)) { throw 'Steam did not exit within 45 seconds.' }
        Start-Sleep -Seconds 2
        Set-SteamOptions $InstallRoot
        Start-Process -FilePath $steamExe
    } elseif (-not $steamWasRunning) {
        Set-SteamOptions $InstallRoot
    } else {
        Write-Warning 'Steam was left running. Exit Steam once for at least five seconds; the background watcher will then save -win for both games.'
    }
}

if (-not $SkipShortcut) {
    $programs = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
    $shortcutPath = Join-Path $programs 'Uninstall RA3 Auto Enhance.lnk'
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = (Join-Path $InstallRoot 'Uninstall.cmd')
    $shortcut.WorkingDirectory = $InstallRoot
    $shortcut.Save()
}

Write-Host 'Installation complete. Launch either game normally from Steam.' -ForegroundColor Green
