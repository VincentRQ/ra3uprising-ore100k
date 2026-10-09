# Security

## Trust boundary

RA3 Auto Enhance is a local, current-user Windows utility. It intentionally:

- reads and writes the exact ore-template scalar for base RA3;
- builds the Uprising override from local retail files and edits only its own startup registration;
- on explicit refill, backs up saves and changes validated OreNode initial, gathered and notification counters in the running Uprising engine;
- changes the game window's standard style and geometry;
- sends arrow-key scan codes only while the matching game owns foreground focus;
- edits the current Steam user's `localconfig.vdf` only while `steam.exe` is stopped;
- registers one current-user scheduled task.

It does not require elevation, inject a DLL, install a driver, contact a server, collect telemetry, or overwrite retail asset archives. It does modify the supported Uprising `.SkuDef` registration, with backups.

## Safe downloads

Use only the repository's GitHub Releases. Each release includes a SHA-256 file. Because the executables are unsigned and use process-memory APIs, antivirus reputation warnings are possible. Inspect and build the MIT-licensed source if you do not trust a binary.

## Reporting a vulnerability

Do not post exploit details in a public issue. Use GitHub's private vulnerability reporting for this repository. Include the affected version, reproduction steps, and expected impact.
