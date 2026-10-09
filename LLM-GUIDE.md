# Uprising ore fix: operating guide

The supported Uprising fix is the retail startup override in version 1.1. The old late template patch is not proof that a mine's current or starting amount changed.

## Authority and inspection

- Source: this repository's default branch and tagged release.
- Runtime: `%USERPROFILE%\.local\share\ra3-auto-enhance`.
- Override, build receipt, configuration backups and refill receipts: `%USERPROFILE%\.local\share\ra3-uprising-ore100k`.
- Logs: `%LOCALAPPDATA%\RA3AutoEnhance`.
- Task: `RA3 Auto Enhance`; inspect its current action before changing processes.
- Two same-named processes can be a PyInstaller bootloader and worker. Do not count them as duplicate independent installs.

Run `RA3OreSetup.exe --check` to verify hash and registration without modifying the game. Confirm the task points to the intended runtime. For a fresh-match report, verify an actual new skirmish mine. For an old-save report, inspect the loaded OreNode counters.

## Recovery

With Uprising closed, `RA3OreSetup.exe --install` builds or reuses the supported override and registers it. The background guard restores only its own missing registration while the game is closed. Unknown versions, a corrupt override and deleted build data require investigation, not blanket numeric replacement or logs labelled success without mine evidence.

For an existing old save, obtain explicit authority to refill its mines, then run `RA3OreRefill.exe --inspect` and `--apply --expected-mines N` with the inspected count. The tool backs up saves and records the old ore counters. Save in-game afterwards to retain the result. Do not restart, discard a match, or load another save merely to verify a refill without the user's permission.

Setup and refill are separate console utilities, not supervisor children. Do not install another repeating ore memory patcher. Preserve unrelated AI mods and their registration entries. Never upload retail BIG files, personal saves, local receipts with user paths, or credentials.

The October 2026 verification records the successful startup override and one-time 24-mine old-save refill. It does not prove every campaign, custom map or third-party mod combination. See `docs/ORE-FIX-VERIFICATION.md`.
