# LLM Guide: RA3 Auto Enhance

Give this file to an AI assistant when you want help installing, verifying, troubleshooting, or developing RA3 Auto Enhance.

## User goal

After one per-user installation, either Steam game should launch normally with:

- borderless, Alt+Tab-safe windowed rendering;
- 100,000-cap ore nodes;
- mouse edge scrolling on all four edges;
- no repeating console windows.

Supported Steam apps and processes:

| Game | Steam app ID | Runtime process |
|---|---:|---|
| Red Alert 3, Community Patch | 17480 | `ra3_1.13.game` |
| Red Alert 3, stock 1.12 | 17480 | `RA3_1.12.game` |
| Red Alert 3: Uprising | 24800 | `ra3ep1_1.1.game` |

## Safety rules for the assistant

1. Ask before closing Steam or a running game unless the user explicitly requested a restart or end-to-end test.
2. Never edit `localconfig.vdf` while `steam.exe` is running.
3. Do not recommend disabling antivirus globally or excluding a broad folder.
4. Do not replace game files or add DLLs to a game directory; this project does neither.
5. Stop only processes whose executable path is inside `%LOCALAPPDATA%\RA3AutoEnhance`.
6. Do not use the old `RA3Enhance.exe` or an ore patcher that replaces every integer/float equal to 30,000. Those implementations are obsolete.
7. Treat a helper log entry as mechanism evidence, not proof of visible camera motion. For final edge-scroll acceptance, test in a live skirmish after the intro camera unlocks.

## Normal installation

Prefer the latest release ZIP, not GitHub's automatic “Source code” ZIP. The release contains the built `bin\` directory.

1. Extract the release.
2. Run `Install.cmd` as the normal desktop user.
3. Let the installer restart Steam once, or fully exit Steam for five seconds.
4. Launch the game through Steam.

No administrator rights or Python installation should be required.

## Canonical paths

```text
Install directory: %LOCALAPPDATA%\RA3AutoEnhance
Logs and state:   %LOCALAPPDATA%\RA3AutoEnhance
Scheduled task:  RA3 Auto Enhance
Steam config:    <Steam>\userdata\<active-user>\config\localconfig.vdf
```

Installed executables:

| Executable | Responsibility |
|---|---|
| `RA3AutoEnhance.exe` | Single-instance supervisor and restart backoff |
| `RA3Borderless.exe` | Removes frame styles and applies monitor overscan |
| `RA3EdgeScroll.exe` | Foreground-only cursor confinement and scan-code arrows |
| `RA3Ore100K.exe` | Exact `{30000,250,60}` to `{100000,250,60}` memory patch |
| `RA3SteamOptions.exe` | Adds/removes installer-owned `-win` options safely |

## Read-only diagnosis

Start with these commands:

```powershell
Get-ScheduledTask -TaskName 'RA3 Auto Enhance' | Select-Object TaskName,State

Get-CimInstance Win32_Process |
  Where-Object { $_.ExecutablePath -like "$env:LOCALAPPDATA\RA3AutoEnhance\*" } |
  Select-Object ProcessId,ParentProcessId,Name,ExecutablePath

Get-ChildItem "$env:LOCALAPPDATA\RA3AutoEnhance\*.log" |
  ForEach-Object { "=== $($_.Name) ==="; Get-Content $_.FullName -Tail 30 }
```

Expected idle state: one supervisor role plus four helper roles, all windowless. PyInstaller's one-file bootloader can display a parent/worker pair for each role in process tools; this is expected. The task state is `Running`. There should be no helper-owned `tasklist.exe`, `cmd.exe`, or `conhost.exe` child.

When a game is running, check its real command line:

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.Name -in @('ra3_1.13.game','RA3_1.12.game','ra3ep1_1.1.game') } |
  Select-Object Name,ProcessId,CommandLine
```

The command line should contain `-win`.

## Acceptance checklist

- [ ] Steam was fully restarted once after installation.
- [ ] The scheduled task is running.
- [ ] The actual `.game` command line contains `-win`.
- [ ] `borderless.log` records the correct game PID and window handle.
- [ ] The window has no caption/frame and fills the monitor with four-pixel overscan.
- [ ] `ore100k.log` records `patched 30000->100000` for the current PID.
- [ ] A live skirmish ore node shows `100,000 / 100,000`.
- [ ] Left, right, top, and bottom edges move the camera.
- [ ] Center cursor position produces no arrow press.
- [ ] Alt+Tab releases cursor clipping and all held arrows.
- [ ] No repeating command windows appear.

## Repository map for maintainers

```text
src/ra3_auto/             canonical Python runtime
installer/                per-user install and uninstall scripts
tools/Build-Release.ps1   tests, PyInstaller builds, package smoke tests, ZIP
tools/Test-Package.ps1    staging install/uninstall test
tests/                    pure unit and Windows-structure tests
.github/workflows/        Windows build and tagged-release automation
```

The release build uses PyInstaller's `--windowed --onefile` mode. The supervisor detects a frozen build and launches the four sibling executables. Source mode uses `pythonw -m ra3_auto.<helper>`.

## Root causes already resolved

- The old edge helper declared only `KEYBDINPUT` inside the Win32 `INPUT` union. That produced a 32-byte structure in a 64-bit helper, while `SendInput` requires 40 bytes. It also sent virtual-key events that RA3's DirectInput path ignored.
- The replacement declares the full input union and sends Set-1 scan codes with `KEYEVENTF_SCANCODE | KEYEVENTF_EXTENDEDKEY`.
- Repeating flashing windows came from helpers spawning `tasklist.exe` in polling loops. The replacement enumerates processes directly with `CreateToolhelp32Snapshot`.
- The ore patcher searches the exact three-field behavior signature instead of replacing every value equal to 30,000.

## Ready-to-paste prompt

```text
Help me with RA3 Auto Enhance using LLM-GUIDE.md as the operating guide. Start with read-only checks. Tell me exactly what is installed, whether the scheduled task and four helpers are healthy, whether my launched game has -win, and what the logs prove. Ask before closing Steam or the game. Do not use the obsolete RA3Enhance.exe or broad 30,000-value patchers.
```
