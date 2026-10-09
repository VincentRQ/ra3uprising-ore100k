# Uprising 100K ore verification

## Root cause and verified behaviour

On 8 October 2026, a fresh Uprising match still showed 30,000 ore after the old helper had successfully patched its cached template. That demonstrated that the template log was insufficient evidence for already-created instances.

The replacement override uses retail linked streams version 7. The named OreNode asset is verified before changing its single capacity scalar from 30,000 to 100,000. The builder retains delivery amounts 250/60 and all other payload bytes. Base, low and medium stream identity/checksum metadata is updated consistently.

After installation and an approved game restart, the user confirmed the new-skirmish fix worked. The generated override's SHA-256 was:

```text
f4a5d38165cf5c360c487708ba471501f5c279d39d8b4240a741c679c470d597
```

The registration guard was tested with a simulated Steam configuration reset, active-game deferral, CRLF readback, unrelated AI registrations and a corrupted override. The hash check rejected corruption before modifying registration.

## Existing save refill

The running retail engine's constructor, serializer and depletion code established that OreNode offset `0x14` stores gathered ore, `0x28` stores initial ore and `0x24` stores its notification state. Remaining ore is initial minus gathered.

Twenty-four attached OreNode instances in the user's older loaded skirmish had initial values of 30,000. A one-time refill backed up original saves, validated module/owner identities, wrote initial 100,000 and gathered zero, and read back **100,000 initial and 100,000 remaining for all 24** while the engine was briefly suspended. Subsequent inspection confirmed initial values stayed 100,000 while normal harvesting reduced remaining amounts.

Original save files were not overwritten. The user was instructed to save in-game to persist the refill. Reload persistence for that newly saved match was not independently tested. The published tool retains the identity checks and additionally requires an explicit mine count and a matching running executable path.

## Reproducible release checks

Run `tools/Build-Release.ps1` for the complete Windows package gate: source tests, seven executable self-tests, bounded supervisor cleanup and isolated install/uninstall staging. Staging skips actual Steam and game modification; unit fixtures exercise registration repair and uninstall separately. GitHub Actions repeats the package gate on a clean Windows runner.

The release includes code and utility executables only. Retail game streams, personal saves, local build receipts and private workstation details are excluded.

## Limits

The startup override is scoped to the supported English Uprising 1.1 retail asset. Base RA3 keeps its older exact-signature template patch. Campaigns, custom maps and other mod combinations were not exhaustively qualified. Generated override deletion, corruption or a game-version change is a repair condition; ordinary restarts and removed registration entries are handled by the persistent guard.
