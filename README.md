# RA3 Uprising: Ore 100K + Edge Scroll

Raises every ore mine's capacity and remaining ore from **30,000 to 100,000** in *Command & Conquer: Red Alert 3 – Uprising*, for every player and AI in skirmish, on all maps, and restores **edge scrolling** (camera pans when the cursor reaches the screen edge) that the SAGE engine only enables in exclusive fullscreen.

## How it works

The ore node capacity (`MaximumGatheredValue`) is data-driven: it lives in `BaseOreNode.xml` and is compiled into the game's binary assets. When a match starts, every ore node instance is seeded from that value.

Two delivery methods are included:

### 1. Live patcher (recommended, verified working)

`Ore100KPatcher.exe` is a small console tool that:

1. Waits for the game process (`ra3ep1_1.1.game`).
2. Waits ~25 seconds for the game's data to load (templates exist by then).
3. Scans the process memory for every value equal to 30,000 (the ore node cap, stored as int and float).
4. Rewrites those values to 100,000.
5. Verifies zero 30,000 values remain and logs the result to `%TEMP%\ore100k-patcher.log`.

Because the type templates are patched before any match starts, every ore node spawned afterwards carries the 100,000 cap and 100,000 remaining, for all players.

The launcher `RA3Uprising-Ore100K.cmd` combines this with the borderless-fullscreen helper (alt-tab safe, no D3D9 device-loss crash) and the edge-scroll tool.

### 3. Edge scrolling (RA3Enhance.exe, verified working)

The SAGE engine only processes mouse-at-screen-edge camera panning in exclusive fullscreen. In windowed/borderless mode it never fires, so alt-tab-safe play loses edge scrolling.

`RA3Enhance.exe` restores it two ways:
1. **Cursor confinement**: while the game has focus, the cursor is clipped inside the game window (no escape to other monitors, reliable edge detection). Released automatically on alt-tab.
2. **Virtual edge scroll**: when the cursor is within 6 pixels of any window edge, the tool holds the matching arrow key. The engine's keyboard camera pan works in windowed mode, so the camera scrolls exactly like fullscreen edge panning, diagonals included. Keys are released the moment the cursor leaves the edge zone or the game loses focus.

Verified in-game: cursor at the right edge pans the camera (screenshot-verified); left edge behaves the same.

### 4. SDK mod (proper mod route, work in progress)

The `mod/` folder contains the RA3 MOD SDK source: `BaseOreNode.xml` (and all 7 concrete ore node types) with `MaximumGatheredValue="100000"`, plus `Mod.xml`. This compiles with `BinaryAssetBuilder.exe` + `MakeBig.exe` into `Ore100K.big`.

Notes on the mod route:
- The compiled big loads (verified: its file list and manifest appear in the game's memory), but the asset override did not take effect in testing, via either `add-big` in the game's `.SkuDef` or a `-modConfig` skudef. The engine appears to keep using the original compiled ore node assets.
- Root cause is suspected to be an asset version/ID mismatch between SDK-compiled assets and the shipped game data. Solving it requires reverse-engineering the big/manifest format further.
- Until then, the live patcher is the reliable path. It produces the same in-game result: mines read `100,000 / 100,000`.

## Files

| File | Purpose |
|---|---|
| `Ore100KPatcher.exe` | The memory patcher (self-contained, no dependencies) |
| `RA3Enhance.exe` | Cursor confinement + virtual edge scrolling |
| `RA3Uprising-Ore100K.cmd` | One-click launcher: borderless + patch + edge scroll |
| `borderless-helper.ps1` | Strips the game window's titlebar, stretches to the monitor |
| `borderless-launcher.ps1` | Starts the helper then the game in windowed mode |
| `src/Ore100KPatcher.cs` | Patcher source (C#, .NET Framework) |
| `src/RA3Enhance.cs` | Edge-scroll + clip source (C#, .NET Framework) |
| `mod/` | RA3 MOD SDK source for the proper-mod route |

## Install

1. Copy the whole folder somewhere stable (e.g. `%LOCALAPPDATA%\RA3Ore100K\`).
2. Edit `RA3Uprising-Ore100K.cmd` if your game is not installed at
   `D:\SteamLibrary\steamapps\common\Command and Conquer Red Alert 3 Uprising\`.
3. Double-click `RA3Uprising-Ore100K.cmd` instead of launching from Steam.

Steam's Play button still launches the unpatched game (30k mines). Always use the launcher.

## Requirements

- Windows 10/11, .NET Framework 4.x (included with Windows)
- Steam version of *Red Alert 3: Uprising* (the game's `.game` process is the 32-bit `ra3ep1_1.1.game`)
- Run the game with `-win` (the launcher does this). Do not run exclusive fullscreen; alt-tab in that mode crashes the SAGE engine.

## Notes

- The patch is applied to the running game's memory only. It does not modify any game files. A fresh launch via the launcher re-applies it automatically.
- Do not run Steam's "Play" for this game while the launcher is also running the game; two instances will fight over the same settings.
- If your antivirus quarantines `Ore100KPatcher.exe` (it is an unsigned, freshly compiled tool), add an exclusion for the folder. A signature-free exe of this kind sometimes trips scanners.
- Some antivirus products in "disinfection" mode can block the patcher's memory reads; wait for the scan to finish before launching.

## Verify

Launch the game via the cmd, start any skirmish, click any ore mine. It reads `100,000 / 100,000`.

The patcher also writes `%TEMP%\ore100k-patcher.log` with a `RESULT: SUCCESS` line when the patch completed cleanly.

## Known limits

- The value is per-process: if the game is restarted, the launcher must run again (it does, automatically).
- The cap applies to ore nodes (the mines on the map). The ore *refinery*'s internal storage buffer is a separate engine constant and was out of scope for this pass.
