using System;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Threading;

// RA3Enhance: cursor clip + virtual edge scroll for C&C Red Alert 3: Uprising
// 1) Confines the cursor to the game window while it is focused (enables
//    reliable edge detection, prevents cursor escape to other monitors).
// 2) Emulates edge scrolling: when the cursor is within EDGE_ZONE pixels of
//    the window edge and the game is focused, holds the corresponding arrow
//    key (keyboard camera pan works in windowed mode, unlike the engine's
//    fullscreen-only mouse-edge path). Release on leaving the zone or on
//    alt-tab.
class RA3Enhance
{
    [DllImport("user32.dll")] static extern bool ClipCursor(ref RECT rect);
    [DllImport("user32.dll")] static extern bool ClipCursor(IntPtr rectNull);
    [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
    [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
    [DllImport("user32.dll")] static extern bool GetCursorPos(out POINT pt);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumWindowsProc cb, IntPtr lParam);
    delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")] static extern uint SendInput(uint n, INPUT[] inputs, int size);

    [StructLayout(LayoutKind.Sequential)]
    struct RECT { public int Left, Top, Right, Bottom; }
    [StructLayout(LayoutKind.Sequential)]
    struct POINT { public int X, Y; }

    [StructLayout(LayoutKind.Sequential)]
    struct INPUT { public uint type; public INPUTUNION u; }
    [StructLayout(LayoutKind.Explicit)]
    struct INPUTUNION { [FieldOffset(0)] public KEYBDINPUT ki; }
    [StructLayout(LayoutKind.Sequential)]
    struct KEYBDINPUT { public ushort wVk; public ushort wScan; public uint dwFlags; public uint time; public IntPtr dwExtraInfo; }

    const uint INPUT_KEYBOARD = 1;
    const uint KEYEVENTF_KEYUP = 0x0002;
    const ushort VK_LEFT = 0x25, VK_UP = 0x26, VK_RIGHT = 0x27, VK_DOWN = 0x28;
    const int EDGE_ZONE = 6; // pixels

    static string LogPath = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "ra3-enhance.log");
    static void Log(string msg)
    {
        try { System.IO.File.AppendAllText(LogPath, DateTime.Now.ToString("HH:mm:ss") + " " + msg + Environment.NewLine); } catch { }
    }

    static void KeyDown(ushort vk) { Send(vk, false); }
    static void KeyUp(ushort vk) { Send(vk, true); }
    static void Send(ushort vk, bool up)
    {
        INPUT[] inp = new INPUT[1];
        inp[0].type = INPUT_KEYBOARD;
        inp[0].u.ki.wVk = vk;
        inp[0].u.ki.dwFlags = up ? KEYEVENTF_KEYUP : 0;
        SendInput(1, inp, Marshal.SizeOf(typeof(INPUT)));
    }

    static int Main(string[] args)
    {
        string processName = args.Length > 0 ? args[0] : "ra3ep1_1.1.game";
        Log("=== RA3Enhance started (pid " + Process.GetCurrentProcess().Id + ") ===");

        Process proc = null;
        DateTime deadline = DateTime.Now.AddSeconds(240);
        while (proc == null && DateTime.Now < deadline)
        {
            Process[] list = Process.GetProcessesByName(processName);
            if (list.Length > 0) proc = list[0];
            else Thread.Sleep(1000);
        }
        if (proc == null) { Log("game process never appeared"); return 1; }
        Log("watching pid " + proc.Id);

        bool clipActive = false;
        bool[] held = new bool[4]; // L U R D
        IntPtr lastWnd = IntPtr.Zero;

        while (true)
        {
            try
            {
                proc.Refresh();
                if (proc.HasExited) break;

                IntPtr gameWnd = IntPtr.Zero;
                EnumWindows((hWnd, lParam) =>
                {
                    uint wpid;
                    GetWindowThreadProcessId(hWnd, out wpid);
                    if (wpid == (uint)proc.Id && IsWindowVisible(hWnd)) { gameWnd = hWnd; return false; }
                    return true;
                }, IntPtr.Zero);

                bool focused = gameWnd != IntPtr.Zero && GetForegroundWindow() == gameWnd;

                if (focused)
                {
                    RECT r;
                    if (GetWindowRect(gameWnd, out r))
                    {
                        if (!clipActive) Log("clip ON at " + r.Left + "," + r.Top + " " + r.Right + "x" + r.Bottom);
                        ClipCursor(ref r);
                        clipActive = true;
                        lastWnd = gameWnd;

                        // virtual edge scroll
                        POINT pt;
                        GetCursorPos(out pt);
                        bool[] want = new bool[4];
                        if (pt.X <= r.Left + EDGE_ZONE) want[0] = true;
                        if (pt.X >= r.Right - 1 - EDGE_ZONE) want[2] = true;
                        if (pt.Y <= r.Top + EDGE_ZONE) want[1] = true;
                        if (pt.Y >= r.Bottom - 1 - EDGE_ZONE) want[3] = true;

                        ushort[] vks = { VK_LEFT, VK_UP, VK_RIGHT, VK_DOWN };
                        for (int i = 0; i < 4; i++)
                        {
                            if (want[i] && !held[i]) { KeyDown(vks[i]); held[i] = true; }
                            else if (!want[i] && held[i]) { KeyUp(vks[i]); held[i] = false; }
                        }
                    }
                }
                else
                {
                    if (clipActive) { ClipCursor(IntPtr.Zero); clipActive = false; Log("clip OFF"); }
                    for (int i = 0; i < 4; i++)
                        if (held[i]) { KeyUp(new ushort[] { VK_LEFT, VK_UP, VK_RIGHT, VK_DOWN }[i]); held[i] = false; }
                }
            }
            catch { }
            Thread.Sleep(30);
        }
        ClipCursor(IntPtr.Zero);
        for (int i = 0; i < 4; i++) if (held[i]) KeyUp(new ushort[] { VK_LEFT, VK_UP, VK_RIGHT, VK_DOWN }[i]);
        Log("=== game exited ===");
        return 0;
    }
}
