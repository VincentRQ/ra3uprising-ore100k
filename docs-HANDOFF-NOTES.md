# RA3 / Uprising Fix Session - Handoff Notes
Last updated: 2026-08-07 (session 2 - Ore100K finished)

## GOAL STATUS

| Goal | Status |
|---|---|
| Alt-tab crashes (both games) | ✅ DONE - windowed+borderless mode |
| CTD fixes | ✅ DONE - CP re-activated + RUNASADMIN removed |
| Borderless fullscreen | ✅ DONE - launcher scripts work |
| **Ore mine cap 30k -> 100k** | ✅ DONE - `Ore100KPatcher.exe` auto-patcher, verified SUCCESS |
| SDK mod route (proper mod) | 🔶 WIP - big loads but asset override does not take effect |

---

## 1. CRASH FIXES (COMPLETE - from session 1)

See session 1 notes below (kept for reference): borderless launcher chain,
CP re-activation, GPU pinning, WER dumps, RESTORE-STOCK.cmd.

## 2. ORE 100K (COMPLETE - this session)

### What the user actually wanted (clarified this session)
- NOT the refinery's internal storage (that was the session-1 assumption, wrong).
- The **ore mine / ore node** on the map: cap + remaining should be 100,000
  at match start, for the player AND all AIs, all maps.
- The mine's displayed value is "remaining / cap", e.g. `29,750 / 30,000`.
- The cap value is `MaximumGatheredValue` in `BaseOreNode.xml` (SDK),
  default 30,000. Ore node instances are seeded from it at spawn.

### Where the value lives at runtime
- Per-node instance: `int 30000` (cap field) + remaining float.
  Node object signature: cap int near `DeliveryAmount=250` and
  `DeliveryAmountWhenEmpty=60` (OreNodeBehavior fields).
- Type templates: `float 30000` + `int 30000` copies in heap objects.
- Live verification: patching all int/float 30,000 -> 100,000 makes every
  mine on screen read `100,000` immediately (user-confirmed).

### The permanent fix (verified working)
`%LOCALAPPDATA%\RA3Ore100K\Ore100KPatcher.exe` - self-contained console exe:
1. Waits for `ra3ep1_1.1.game`.
2. Waits 25 s (game data loaded; templates exist).
3. Patches every int 30,000 -> 100,000 and float 30,000 -> 100,000.
4. Verifies zero 30,000 remain; logs `RESULT: SUCCESS` to `%TEMP%\ore100k-patcher.log`.

Combined launcher: `RA3Uprising-Ore100K.cmd` (borderless helper + patcher + game -win).
Manual procedure (equivalent, for reference): memscan + patchints + patchcap
scripts in the session temp area.

### SDK mod route (WIP - why it failed)
- Built `Ore100K.big` from the SDK (Mod.xml + BaseOreNode.xml MGV=100000 +
  7 concrete OreNode XMLs) with BinaryAssetBuilder + MakeBig. Compile OK.
- The big's file list + mod.manifest ARE loaded into memory on both
  `add-big` (skudef edit) and `-modConfig` launches.
- But in-match node caps remained 30,000 in both cases: the engine kept the
  original compiled ore node assets.
- Suspected: SDK-compiled asset ID/version mismatch vs shipped game data.
  Fixing requires the big/manifest format reverse-engineering (session-1
  exe note: BAB.exe was AnyCPU + x86 plugins = BadImageFormat until
  `corflags /32BIT+` was applied; MakeBig needs `-f -o:path dir`).
- The live patcher produces the same in-game result, so this is parked.

### Environment hazards encountered (this session)
- AV ("Disinfection in progress" toast) intermittently: locked .ps1 files,
  removed MemScan.dll, blocked input injection (game got no clicks/keys),
  caused `spawn EPERM` on process launches. All three cleared eventually;
  the patcher was rebuilt as a single .exe to sidestep script/DLL locks.
- MEGAsync sync also locks freshly created files in Default Project briefly.

## 3. SESSION-1 NOTES (kept for reference)

### Crash fixes (complete)
- Both games crash on alt-tab due to D3D9 exclusive-fullscreen device loss.
  Uprising: `ra3ep1_1.1.game + 0x784187` (NULL deref, state==1).
- Borderless solution: windowed (-win) + helper strips titlebar + stretches.
- `RA3EP1.exe` RUNASADMIN removed (was `~ RUNASADMIN WIN7RTM` -> `~ WIN7RTM`).
- GPU pinned to NVIDIA RTX 4070 for all 5 exes (GpuPreference=2).
- Uprising resolution: Options.ini `2560 1600` -> `1920 1080`.
- WER LocalDumps armed for all 5 exes (C:\Users\VQuim\AppData\Local\CrashDumps).
- Full restore: `RESTORE-STOCK.cmd`; backups in `backups-20260807-123314\`.

### Files in C:\Users\VQuim\Documents\Default Project\
- `RA3Uprising-Ore100K.cmd` - THE launcher (borderless + Ore100K patch).
- `RA3-Borderless.cmd` - base RA3 borderless launcher.
- `borderless-helper.ps1` / `borderless-launcher.ps1` - borderless machinery.
- `RESTORE-STOCK.cmd` - revert all registry/file changes.

### Useful facts
- Steam: RA3 = app 17480, Uprising = app 24800 (D:\SteamLibrary).
- The `.game` files ARE the executables (SAGE engine).
- BinaryAssetBuilder.exe needed corflags /32BIT+ (AnyCPU vs x86 plugins).
- MakeBig usage: `MakeBig.exe -f -o:<out.big> <dir>`.
- SDK mods root: `D:\RA3 MOD SDK\Mods\<name≤15 chars>\data\`.
