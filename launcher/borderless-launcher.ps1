param(
    [Parameter(Mandatory=$true)][string]$ProcessName,
    [Parameter(Mandatory=$true)][string]$GameExe,
    [string]$GameArgs = "-win"
)

# Borderless launcher for RA3 / Uprising (Steam)
# Uses 8.3 short paths so Start-Process doesn't mangle the arguments.
# Launches the helper (detached) then the game windowed (-win):
#   - alt-tab can never trigger the D3D9 exclusive-fullscreen device-loss crash
#   - the helper removes the titlebar + stretches to the monitor = borderless fullscreen

$short = "C:\Users\VQuim\DOCUME~1\DEFAUL~1"
$helper = "$short\borderless-helper.ps1"

Start-Process -FilePath "powershell.exe" -ArgumentList @(
    '-NoProfile','-ExecutionPolicy','Bypass','-File',$helper,'-ProcessName',$ProcessName
)
Start-Sleep -Milliseconds 500
Start-Process -FilePath $GameExe -ArgumentList $GameArgs
