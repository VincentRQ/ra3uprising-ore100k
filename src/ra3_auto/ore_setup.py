"""Build the ore override from the owner's game, register it, or remove its entry."""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import winreg

from ra3_auto.ore_disk import ROOT, DiskOverride, registration
from ra3_auto.processes import find_first_process


def discover_game():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam') as key:
            steam = Path(winreg.QueryValueEx(key, 'SteamPath')[0])
    except OSError:
        return None
    roots = [steam]
    libraries = steam / 'steamapps/libraryfolders.vdf'
    if libraries.exists():
        roots.extend(Path(value.replace('\\\\', '\\')) for value in
                     re.findall(r'"path"\s+"([^"]+)"', libraries.read_text(encoding='utf-8-sig')))
    for root in dict.fromkeys(roots):
        manifest = root / 'steamapps/appmanifest_24800.acf'
        if not manifest.exists():
            continue
        match = re.search(r'"installdir"\s+"([^"]+)"', manifest.read_text(encoding='utf-8-sig'))
        if match:
            game = root / 'steamapps/common' / match.group(1)
            if (game / 'Data/ra3ep1_1.1.game').is_file():
                return game.resolve()
    return None


def uninstall_registration(guard):
    if find_first_process(['ra3ep1_1.1.game'])[0]:
        raise RuntimeError('Close Uprising before removing its ore override')
    original = guard.config.read_bytes()
    text = original.decode('utf-8-sig')
    own_line = 'add-big ' + str(guard.path)
    lines = text.splitlines(keepends=True)
    updated = ''.join(line for line in lines if line.strip() != own_line)
    if updated != text:
        from datetime import datetime, timezone
        backup = ROOT / 'backups'
        backup.mkdir(exist_ok=True)
        (backup / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-uninstall.SkuDef')).write_bytes(original)
        temporary = guard.config.with_suffix('.ore100k.tmp')
        temporary.write_bytes(updated.encode('utf-8'))
        os.replace(temporary, guard.config)
        if guard.config.read_bytes().decode('utf-8-sig') != updated:
            raise RuntimeError('Ore uninstall registration read-back failed')
    # Keep locally generated assets and backups for recovery, but disable guard.
    receipt = ROOT / 'build-receipt.json'
    os.replace(receipt, ROOT / 'uninstalled-build-receipt.json')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    for option in ('install', 'check', 'uninstall', 'self-test'):
        actions.add_argument('--' + option, action='store_true')
    parser.add_argument('--game-dir', type=Path)
    args = parser.parse_args()
    if args.self_test:
        assert registration('set-exe Data\\ra3ep1_1.1.game\n', Path('Ore.big')).splitlines()[1] == 'add-big Ore.big'
        return 0
    if args.uninstall:
        if (ROOT / 'build-receipt.json').exists():
            uninstall_registration(DiskOverride())
        return 0
    if args.check:
        guard = DiskOverride()
        guard.verify()
        text = guard.config.read_bytes().decode('utf-8-sig')
        if registration(text, guard.path) != text:
            raise RuntimeError('Ore registration is missing or has lower priority')
        print('Retail ore override verified and registered')
        return 0
    game = args.game_dir.resolve() if args.game_dir else discover_game()
    if game is None:
        print('Uprising not found. Use --game-dir with its installation folder.')
        return 2
    if find_first_process(['ra3ep1_1.1.game'])[0]:
        raise RuntimeError('Close Uprising before installing the startup ore override')
    if not (game / 'RA3EP1_english_1.1.SkuDef').is_file():
        raise RuntimeError('Requires the supported English Uprising 1.1 configuration')
    if not (ROOT / 'build-receipt.json').exists():
        disabled = ROOT / 'uninstalled-build-receipt.json'
        if disabled.exists():
            previous = json.loads(disabled.read_text(encoding='utf-8'))
            if Path(previous['game']).resolve() != game:
                raise RuntimeError('A retained override belongs to another installation')
            os.replace(disabled, ROOT / 'build-receipt.json')
        else:
            from ra3_auto.ore_build import build_override
            build_override(game)
    guard = DiskOverride()
    if Path(guard.receipt['game']).resolve() != game:
        raise RuntimeError('An override is already configured for a different installation')
    print(guard.ensure())
    print('Start Uprising normally; new matches use 100,000 ore.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
