# RA3 Auto Enhance

No-admin Windows enhancements for the Steam versions of:

- *Command & Conquer: Red Alert 3* (including the Community Patch executable)
- *Command & Conquer: Red Alert 3 – Uprising*

Install once, then launch either game normally from Steam. RA3 Auto Enhance supplies:

- **100K ore mines** — raises the ore-node cap from 30,000 to 100,000 for every player and AI.
- **Borderless fullscreen** — keeps the game internally windowed for safer Alt+Tab behavior, removes the frame, and fills the active monitor.
- **Working edge scrolling** — restores mouse-at-edge camera movement in borderless mode, including diagonals.
- **Steam Play-button support** — safely persists `-win` for Steam app IDs `17480` and `24800`.
- **No flashing helper windows** — the installed runtime uses Windows GUI-subsystem executables and native process enumeration; it does not loop through `tasklist.exe` or `cmd.exe`.

## Install

1. Open the repository's [Releases](https://github.com/VincentRQ/ra3uprising-ore100k/releases) page.
2. Download the newest `RA3-Auto-Enhance-<version>.zip` and its `.sha256` file.
3. Extract the ZIP completely.
4. Double-click `Install.cmd`.
5. Allow the installer to restart Steam once, or exit Steam manually for at least five seconds and reopen it.
6. Launch either game normally from the Steam Library.

The installer does not need administrator rights. It installs to:

```text
%LOCALAPPDATA%\RA3AutoEnhance
```

It registers one current-user scheduled task named `RA3 Auto Enhance`. That task starts one hidden supervisor at sign-in; the supervisor starts four hidden helpers for borderless mode, edge scrolling, ore patching, and Steam launch options.

## Uninstall

Use **Uninstall RA3 Auto Enhance** from the Start menu, or run `Uninstall.cmd` from the extracted release folder.

The uninstaller removes the scheduled task, installed files, and only the `-win` launch-option tokens that this installer recorded as its own. If Steam is open, it asks before closing it.

## What it changes

RA3 Auto Enhance does **not** replace or edit game files.

At runtime it:

1. Detects `ra3_1.13.game`, `RA3_1.12.game`, or `ra3ep1_1.1.game` with the Windows Toolhelp API.
2. Removes standard window frame styles and applies a four-pixel monitor overscan.
3. Clips the cursor only while the game owns foreground focus and sends DirectInput-compatible arrow scan codes at monitor edges.
4. Finds the exact ore behavior signature `{30000, 250, 60}` in the running process and changes only its first value to `100000`.
5. Adds `-win` to the two Steam app records while Steam is not writing `localconfig.vdf`. A backup is created beside that file before the first change.

## Security and antivirus notice

The ore feature must call Windows process-memory APIs (`OpenProcess`, `ReadProcessMemory`, and `WriteProcessMemory`). Unsigned tools that do this can trigger antivirus or reputation warnings even when their source is public.

- Download releases only from this repository.
- Compare the ZIP's SHA-256 hash with the published `.sha256` file.
- Do not disable antivirus globally or add broad folder exclusions.
- If you prefer, inspect the source and build the executables locally.

See [SECURITY.md](SECURITY.md) for the exact trust boundary and reporting guidance.

## Logs and troubleshooting

Runtime logs and installer-owned state live in:

```text
%LOCALAPPDATA%\RA3AutoEnhance
```

Useful files:

| File | Meaning |
|---|---|
| `supervisor.log` | Helper starts, stops, and restart backoff |
| `borderless.log` | Window detection and geometry application |
| `edge-scroll.log` | Game attachment, cursor clipping, and arrow press/release events |
| `ore100k.log` | Game attachment and the exact patched address |
| `steam-options.log` | Steam config discovery, backup, add, and removal operations |
| `state.json` | Records which Steam options the installer owns |

Quick checks:

```powershell
Get-ScheduledTask -TaskName 'RA3 Auto Enhance'
Get-Content "$env:LOCALAPPDATA\RA3AutoEnhance\supervisor.log" -Tail 20
Get-Content "$env:LOCALAPPDATA\RA3AutoEnhance\ore100k.log" -Tail 20
Get-Content "$env:LOCALAPPDATA\RA3AutoEnhance\edge-scroll.log" -Tail 20
```

If Steam Play launches exclusive fullscreen, exit Steam completely, wait five seconds, and reopen it. The helper never edits `localconfig.vdf` while `steam.exe` is running.

For AI-assisted setup or diagnosis, open [LLM-GUIDE.md](LLM-GUIDE.md) and give it to the assistant.

## Build from source

Requirements:

- Windows 10 or 11
- Python 3.11+
- PowerShell 5.1+

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\tools\Build-Release.ps1 -Version 1.0.0 -Python .\.venv\Scripts\python.exe
```

The build runs unit tests, creates five windowless executables with PyInstaller, runs each executable's self-test, performs a clean staging install/uninstall, then creates a ZIP and SHA-256 file under `artifacts\`.

## Supported scope

- Steam releases on Windows 10/11.
- Base RA3 process names: `ra3_1.13.game` and `RA3_1.12.game`.
- Uprising process name: `ra3ep1_1.1.game`.
- The ore cap applies to map ore nodes. A refinery's separate internal buffer is outside this project's scope.
- The exact live patcher is the verified ore path; no game assets or SDK files are distributed.

## License

Code in this repository is released under the [MIT License](LICENSE). *Command & Conquer*, *Red Alert 3*, and related names are trademarks of their respective owners. This is an independent fan project and is not affiliated with or endorsed by Electronic Arts or Valve.
