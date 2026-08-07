param(
    [Parameter(Mandatory=$true)][string]$ProcessName,
    [string]$WindowTitle = ""
)

# Borderless fullscreen helper for SAGE-engine games (RA3 / Uprising)
# Removes the titlebar from the game window and stretches it to fill the monitor.
# Polls so it survives window recreation; exits when the game exits.

$ProcessNames = $ProcessName -split ',' | ForEach-Object { $_.Trim() }
$log = Join-Path $PSScriptRoot 'borderless-helper.log'
function Log($msg) {
    try { "$((Get-Date).ToString('HH:mm:ss')) $msg" | Out-File -FilePath $log -Append -Encoding utf8 -ErrorAction Stop } catch {}
}
try { Log "helper started, watching: $($ProcessNames -join ',')" } catch {}

try {
    Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;

public class Borderless {
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern IntPtr GetWindow(IntPtr hWnd, uint uCmd);
    [DllImport("user32.dll")] public static extern int GetWindowLong(IntPtr hWnd, int nIndex);
    [DllImport("user32.dll")] public static extern int SetWindowLong(IntPtr hWnd, int nIndex, int dwNewLong);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);
    [DllImport("user32.dll")] public static extern IntPtr MonitorFromWindow(IntPtr hwnd, uint dwFlags);
    [DllImport("user32.dll")] public static extern bool GetMonitorInfo(IntPtr hMonitor, ref MONITORINFO lpmi);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);

    public const int GWL_STYLE = -16;
    public const int WS_CAPTION = 0x00C00000;
    public const int WS_THICKFRAME = 0x00040000;
    public const int WS_BORDER = 0x00800000;
    public const int WS_DLGFRAME = 0x00400000;
    public const int WS_MAXIMIZEBOX = 0x00010000;
    public const int WS_MINIMIZEBOX = 0x00020000;
    public const int WS_SYSMENU = 0x00080000;
    public const uint SWP_NOZORDER = 0x0004;
    public const uint SWP_NOACTIVATE = 0x0010;
    public const uint SWP_FRAMECHANGED = 0x0020;
    public const uint MONITOR_DEFAULTTONEAREST = 2;

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left, Top, Right, Bottom; }
    [StructLayout(LayoutKind.Sequential)]
    public struct MONITORINFO {
        public int cbSize;
        public RECT rcMonitor;
        public RECT rcWork;
        public uint dwFlags;
    }

    public static IntPtr FindWindowForPid(uint pid) {
        IntPtr found = IntPtr.Zero;
        EnumWindows((hWnd, lParam) => {
            uint wpid;
            GetWindowThreadProcessId(hWnd, out wpid);
            if (wpid == pid && IsWindowVisible(hWnd)) {
                if (GetWindow(hWnd, 4) == IntPtr.Zero) { // GW_OWNER
                    found = hWnd;
                    return false;
                }
            }
            return true;
        }, IntPtr.Zero);
        return found;
    }

    public static string GetTitle(IntPtr hWnd) {
        var sb = new StringBuilder(256);
        GetWindowText(hWnd, sb, 256);
        return sb.ToString();
    }

    public static void MakeBorderless(IntPtr hWnd) {
        int style = GetWindowLong(hWnd, GWL_STYLE);
        style &= ~(WS_CAPTION | WS_THICKFRAME | WS_BORDER | WS_DLGFRAME | WS_MAXIMIZEBOX | WS_MINIMIZEBOX | WS_SYSMENU);
        SetWindowLong(hWnd, GWL_STYLE, style);

        var mi = new MONITORINFO();
        mi.cbSize = System.Runtime.InteropServices.Marshal.SizeOf(typeof(MONITORINFO));
        IntPtr mon = MonitorFromWindow(hWnd, MONITOR_DEFAULTTONEAREST);
        GetMonitorInfo(mon, ref mi);

        SetWindowPos(hWnd, IntPtr.Zero,
            mi.rcMonitor.Left, mi.rcMonitor.Top,
            mi.rcMonitor.Right - mi.rcMonitor.Left,
            mi.rcMonitor.Bottom - mi.rcMonitor.Top,
            SWP_FRAMECHANGED | SWP_NOZORDER | SWP_NOACTIVATE);
    }
}
"@ -ErrorAction Stop
    Log "Add-Type OK"
} catch {
    Log "Add-Type FAILED: $($_.Exception.Message)"
    exit 2
}

function Get-GameProc {
    foreach ($n in $ProcessNames) {
        $p = Get-Process -Name $n -ErrorAction SilentlyContinue
        if ($p) { return $p }
        $base = $n -replace '\.game$', ''
        $p = Get-Process -Name $base -ErrorAction SilentlyContinue
        if ($p) { return $p }
        $p = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Name -eq $n -or $_.Name -eq $base }
        if ($p) { return $p }
    }
    return $null
}

$proc = Get-GameProc
if (-not $proc) {
    Log "waiting for game process"
    $deadline = (Get-Date).AddMinutes(5)
    while (-not $proc -and (Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 500
        $proc = Get-GameProc | Select-Object -First 1
    }
    if (-not $proc) { Log "game process never appeared"; exit 1 }
}

Log "attaching to $($proc.ProcessName) (pid $($proc.Id))"

$applied = $false
$lastHwnd = [IntPtr]::Zero
while ($proc) {
    try {
        $hWnd = [Borderless]::FindWindowForPid([uint32]$proc.Id)
        if ($hWnd -ne [IntPtr]::Zero) {
            if (-not [Borderless]::IsWindowVisible($hWnd)) {
                if ($applied) { Log "window hidden; waiting" }
                $applied = $false
            } elseif ([Borderless]::IsIconic($hWnd)) {
                if ($applied) { Log "window minimized; waiting" }
                $applied = $false
            } else {
                if (-not $applied -or $hWnd -ne $lastHwnd) {
                    $title = [Borderless]::GetTitle($hWnd)
                    Log "window found: $title (hwnd=$hWnd)"
                }
                [Borderless]::MakeBorderless($hWnd)
                $applied = $true
                $lastHwnd = $hWnd
            }
        }
    } catch {
        Log "poll error: $($_.Exception.Message)"
    }
    Start-Sleep -Milliseconds 500
    $proc = Get-GameProc | Select-Object -First 1
}
Log "game exited. done."


