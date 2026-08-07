using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

class Ore100KPatcher
{
    // --- native imports ---
    [DllImport("kernel32.dll")] static extern IntPtr OpenProcess(uint access, bool inherit, int pid);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
    [DllImport("kernel32.dll")] static extern bool VirtualQueryEx(IntPtr h, IntPtr addr, out MBI info, int len);
    [DllImport("kernel32.dll")] static extern bool ReadProcessMemory(IntPtr h, IntPtr addr, byte[] buf, int size, out int read);
    [DllImport("kernel32.dll")] static extern bool WriteProcessMemory(IntPtr h, IntPtr addr, byte[] buf, int size, out int written);

    [StructLayout(LayoutKind.Sequential)]
    struct MBI
    {
        public IntPtr BaseAddress;
        public IntPtr AllocationBase;
        public uint AllocationProtect;
        public IntPtr RegionSize;
        public uint State;
        public uint Protect;
        public uint Type;
    }

    const uint PROCESS_ALL_ACCESS = 0x0438;
    const uint MEM_COMMIT = 0x1000;
    const uint PAGE_READWRITE = 0x04;
    const uint PAGE_WRITECOPY = 0x08;
    const uint PAGE_EXECUTE_READWRITE = 0x40;

    static List<long> ScanInt(IntPtr h, int target)
    {
        byte[] needle = BitConverter.GetBytes(target);
        var hits = new List<long>();
        IntPtr addr = IntPtr.Zero;
        MBI mbi;
        byte[] buf = new byte[16384];
        while (VirtualQueryEx(h, addr, out mbi, Marshal.SizeOf(typeof(MBI))) != false)
        {
            long size = mbi.RegionSize.ToInt64();
            long baseAddr = mbi.BaseAddress.ToInt64();
            if (size > 0 && (mbi.State & MEM_COMMIT) != 0 &&
                ((mbi.Protect & PAGE_READWRITE) != 0 || (mbi.Protect & PAGE_WRITECOPY) != 0 || (mbi.Protect & PAGE_EXECUTE_READWRITE) != 0))
            {
                long remaining = size, offset = 0;
                while (remaining > 0)
                {
                    int chunk = (int)Math.Min(remaining, buf.Length);
                    int read = 0;
                    if (ReadProcessMemory(h, new IntPtr(baseAddr + offset), buf, chunk, out read) && read >= 4)
                    {
                        for (int i = 0; i <= read - 4; i++)
                            if (buf[i] == needle[0] && buf[i+1] == needle[1] && buf[i+2] == needle[2] && buf[i+3] == needle[3])
                                hits.Add(baseAddr + offset + i);
                    }
                    offset += chunk;
                    remaining -= chunk;
                }
            }
            long next = baseAddr + size;
            if (next <= addr.ToInt64()) break;
            addr = new IntPtr(next);
        }
        return hits;
    }

    static List<long> ScanFloat(IntPtr h, float target)
    {
        byte[] needle = BitConverter.GetBytes(target);
        var hits = new List<long>();
        IntPtr addr = IntPtr.Zero;
        MBI mbi;
        byte[] buf = new byte[16384];
        while (VirtualQueryEx(h, addr, out mbi, Marshal.SizeOf(typeof(MBI))) != false)
        {
            long size = mbi.RegionSize.ToInt64();
            long baseAddr = mbi.BaseAddress.ToInt64();
            if (size > 0 && (mbi.State & MEM_COMMIT) != 0 &&
                ((mbi.Protect & PAGE_READWRITE) != 0 || (mbi.Protect & PAGE_WRITECOPY) != 0 || (mbi.Protect & PAGE_EXECUTE_READWRITE) != 0))
            {
                long remaining = size, offset = 0;
                while (remaining > 0)
                {
                    int chunk = (int)Math.Min(remaining, buf.Length);
                    int read = 0;
                    if (ReadProcessMemory(h, new IntPtr(baseAddr + offset), buf, chunk, out read) && read >= 4)
                    {
                        for (int i = 0; i <= read - 4; i++)
                            if (buf[i] == needle[0] && buf[i+1] == needle[1] && buf[i+2] == needle[2] && buf[i+3] == needle[3])
                                hits.Add(baseAddr + offset + i);
                    }
                    offset += chunk;
                    remaining -= chunk;
                }
            }
            long next = baseAddr + size;
            if (next <= addr.ToInt64()) break;
            addr = new IntPtr(next);
        }
        return hits;
    }

    static string LogPath = Path.Combine(Path.GetTempPath(), "ore100k-patcher.log");
    static void Log(string msg)
    {
        try { File.AppendAllText(LogPath, DateTime.Now.ToString("HH:mm:ss") + " " + msg + Environment.NewLine); } catch { }
    }

    static int Main(string[] args)
    {
        string processName = args.Length > 0 ? args[0] : "ra3ep1_1.1.game";
        int delay = args.Length > 1 ? int.Parse(args[1]) : 25;
        int timeoutSec = args.Length > 2 ? int.Parse(args[2]) : 240;
        Log("=== Ore100KPatcher started (pid " + Process.GetCurrentProcess().Id + ") ===");

        // wait for the game process
        Process proc = null;
        DateTime deadline = DateTime.Now.AddSeconds(timeoutSec);
        while (proc == null && DateTime.Now < deadline)
        {
            Process[] list = Process.GetProcessesByName(processName);
            if (list.Length > 0) proc = list[0];
            else Thread.Sleep(1000);
        }
        if (proc == null) { Log("ERROR: game process never appeared"); return 1; }
        Log("attached to pid " + proc.Id + "; waiting " + delay + "s for data load");
        Thread.Sleep(delay * 1000);
        try { if (proc.HasExited) { Log("ERROR: game exited"); return 1; } } catch { }

        IntPtr h = OpenProcess(PROCESS_ALL_ACCESS, false, proc.Id);
        if (h == IntPtr.Zero) { Log("ERROR: OpenProcess failed, last error " + Marshal.GetLastWin32Error()); return 1; }

        // int 30000 -> 100000
        try
        {
            List<long> ints = ScanInt(h, 30000);
            Log("int 30000 x " + ints.Count);
            int ok = 0;
            foreach (long a in ints)
            {
                int written = 0;
                if (WriteProcessMemory(h, new IntPtr(a), BitConverter.GetBytes((int)100000), 4, out written)) ok++;
            }
            Log("int patch ok " + ok + " / " + ints.Count);
        }
        catch (Exception e) { Log("ERROR in int patch: " + e.Message); }

        // float 30000 -> 100000
        try
        {
            List<long> floats = ScanFloat(h, 30000f);
            Log("float 30000 x " + floats.Count);
            int ok = 0;
            foreach (long a in floats)
            {
                int written = 0;
                if (WriteProcessMemory(h, new IntPtr(a), BitConverter.GetBytes(100000f), 4, out written)) ok++;
            }
            Log("float patch ok " + ok + " / " + floats.Count);
        }
        catch (Exception e) { Log("ERROR in float patch: " + e.Message); }

        // verify
        try
        {
            int i2 = ScanInt(h, 30000).Count;
            int f2 = ScanFloat(h, 30000f).Count;
            Log("verify: int 30000 remaining x " + i2 + ", float 30000 remaining x " + f2);
            if (i2 == 0 && f2 == 0) Log("RESULT: SUCCESS - all ore node caps raised to 100000");
            else Log("RESULT: PARTIAL - " + i2 + " int + " + f2 + " float 30000 values remain");
        }
        catch (Exception e) { Log("ERROR in verify: " + e.Message); }

        CloseHandle(h);
        Log("=== done ===");
        return 0;
    }
}
