# RA3 Auto Enhance — persistent Uprising 100K ore fix

Install once, then launch Red Alert 3 or Uprising normally from Steam. Includes borderless fullscreen, edge scrolling and Steam `-win` options. **Uprising 1.1 ore mines start at 100,000 for every player and AI.**

## Install

1. Download the latest ZIP and SHA-256 file from [Releases](https://github.com/VincentRQ/ra3uprising-ore100k/releases).
2. Extract the ZIP completely and close Uprising.
3. Run `Install.cmd`. The installer locates Uprising through Steam and builds the override from your own retail files. No SDK installation or Python is needed for the packaged installer.
4. Restart Steam once to load its updated launch options, then use the normal Steam Play button.

Runtime executables are installed under `%USERPROFILE%\.local\share\ra3-auto-enhance`. One current-user scheduled task, `RA3 Auto Enhance`, starts the supervisor and four background helpers at sign-in. Setup and refill tools run only when requested. Updating from the old installer stops its recognised supervisor and helpers before starting the new bundle.

If Uprising is outside the detected Steam libraries, run this from a terminal in the installed runtime folder:

```powershell
.\RA3OreSetup.exe --install --game-dir "D:\SteamLibrary\steamapps\common\Command and Conquer Red Alert 3 Uprising"
```

Use the actual installation folder on your computer. Setup supports the English retail Uprising 1.1 configuration and the verified native OreNode asset. It refuses unknown asset versions instead of guessing.

## Why the 30K fix used to fail

The old helper edited an ore template after the engine loaded it. A match or old save could already have created its own 30,000-ore instances. A successful template-write log therefore did not prove that a mine had changed.

Version 1.1 builds a **retail-native startup override**. It changes only the named OreNode capacity and required identity/checksum metadata, retaining the original retail streams. The override is registered before the stock stream in the game's `.SkuDef`, so fresh mines are created with 100,000 ore. Uprising no longer relies on late memory-template scans.

The background guard verifies the generated file and repairs a missing registration after Steam file verification, when the game is closed. It preserves other mod entries. Local override data, receipts and configuration backups are kept under `%USERPROFILE%\.local\share\ra3-uprising-ore100k`.

This is persistent across ordinary restarts and registration resets. If the generated override is deleted or corrupted, or the retail game version changes, setup needs repair; the helper logs the failure. It does not silently fall back to the old Uprising patcher.

## Older saved games

Old saves retain their own initial and depleted ore counters. The startup fix does not refill an existing match automatically.

Load the desired save and run the one-time inspection from the installed runtime folder:

```powershell
.\RA3OreRefill.exe --inspect
```

Count the identified mines, then supply that count explicitly. For the tested 24-mine map:

```powershell
.\RA3OreRefill.exe --apply --expected-mines 24
```

The tool validates the retail engine routines, the running executable path, OreNode module and owner identities, and each owner's module membership. It backs up original Uprising saves and records the previous counters before briefly suspending the engine for the writes. It sets starting ore to 100,000, clears mined ore, verifies the result and resumes the match. It never replaces arbitrary occurrences of 30,000.

**Save the match in-game after refilling.** That saves the new counters for later loading. Harvesting continues to reduce the remaining amount normally. The refill tool does not edit save files directly and does not keep refilling mines in the background. Use `--game-dir` or `--saves-dir` if discovery or the standard Saved Games location does not match your installation.

## Check and recover

From the installed runtime folder:

```powershell
.\RA3OreSetup.exe --check
Get-ScheduledTask -TaskName 'RA3 Auto Enhance'
Get-Content "$env:LOCALAPPDATA\RA3AutoEnhance\ore100k.log" -Tail 20
```

After setup, start a **new skirmish** and select a mine: starting ore should be 100,000 and remaining ore should begin at 100,000 before harvesting. Old saves require the separate refill above. A refinery's internal storage buffer is outside this fix's scope.

Use `Uninstall.cmd` or the Start-menu uninstaller to remove the helpers and their scheduled task. Close Uprising first. Uninstall removes only this override's registration and installer-owned Steam options; local override files and backups are retained for recovery.

## Build and verification

Windows 10/11, Python 3.11+ and PowerShell 5.1+:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\tools\Build-Release.ps1 -Version 1.1.0 -Python .\.venv\Scripts\python.exe
```

The build runs unit tests, packages seven executables, runs their self-tests, checks supervisor cleanup and verifies staged installation/uninstallation before producing a ZIP and SHA-256 file. Retail assets are built on the owner's machine and are excluded from GitHub and release packages.

See [the verification record](docs/ORE-FIX-VERIFICATION.md), [LLM-GUIDE.md](LLM-GUIDE.md), and [SECURITY.md](SECURITY.md). Base Red Alert 3 retains the exact-signature memory-template patch; the persistent retail override and old-save refill described here target Uprising 1.1.

## Licence

[MIT](LICENSE) for this project's code. Command & Conquer and Red Alert 3 belong to their respective owners. Independent fan project, not affiliated with Electronic Arts or Valve. Never disable antivirus globally to install it; compare release hashes or build the source yourself.
