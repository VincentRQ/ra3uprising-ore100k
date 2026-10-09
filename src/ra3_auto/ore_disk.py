"""Verify and maintain the locally built, retail-native Uprising ore override."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os

ROOT = Path.home() / '.local' / 'share' / 'ra3-uprising-ore100k'


def registration(text, override):
    line = 'add-big ' + str(override)
    lines = text.splitlines()
    # Own this one registration only; preserve AI, other mods and launch data.
    matches = [i for i, value in enumerate(lines) if value.strip() == line]
    if len(matches) == 1 and matches[0] == 1:
        return text
    if not lines or lines[0].strip().casefold() != 'set-exe data\\ra3ep1_1.1.game':
        raise ValueError('Unsupported Uprising configuration; refusing an automatic edit')
    lines = [value for value in lines if value.strip() != line]
    lines.insert(1, line)
    newline = '\r\n' if '\r\n' in text else '\n'
    return newline.join(lines) + newline


class DiskOverride:
    def __init__(self):
        self.receipt = json.loads((ROOT / 'build-receipt.json').read_text(encoding='utf-8'))
        self.path = Path(self.receipt['override'])
        if self.path.resolve().parent != ROOT.resolve():
            raise ValueError('Override must remain in its canonical local directory')
        self.config = Path(self.receipt['game']) / 'RA3EP1_english_1.1.SkuDef'
        self.checked_stat = None

    def verify(self):
        state = self.path.stat()
        identity = (state.st_size, state.st_mtime_ns)
        if identity != self.checked_stat:
            digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
            if digest != self.receipt['override_sha256']:
                raise ValueError('Ore override integrity check failed')
            self.checked_stat = identity

    def ensure(self, *, game_running=False):
        self.verify()
        original = self.config.read_bytes()
        text = original.decode('utf-8-sig')
        updated = registration(text, self.path)
        if text == updated:
            return 'registered'
        if game_running:
            return 'registration deferred until the game closes'
        backups = ROOT / 'backups'
        backups.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        (backups / (stamp + '.SkuDef')).write_bytes(original)
        temporary = self.config.with_suffix(self.config.suffix + '.ore100k.tmp')
        temporary.write_bytes(updated.encode('utf-8'))
        os.replace(temporary, self.config)
        if self.config.read_bytes().decode('utf-8-sig') != updated:
            raise RuntimeError('Ore registration read-back failed')
        return 'registration restored'
