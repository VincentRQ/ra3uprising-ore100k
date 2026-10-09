import importlib.util
from pathlib import Path
import struct
import sys
import unittest
import tempfile
import json
import hashlib
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from ra3_auto.ore_disk import registration, DiskOverride
from ra3_auto import ore_build as builder


class PermanentOreTests(unittest.TestCase):
    def test_changes_only_exact_ore_capacity(self):
        payload = b'\x99' * 28 + builder.STOCK + struct.pack('<I', 30000) + b'\x99' * 20
        changed, offset = builder.patch_payload(payload)
        self.assertEqual(28, offset)
        self.assertEqual(builder.PATCHED, changed[28:40])
        self.assertEqual(payload[:28], changed[:28])
        self.assertEqual(payload[32:], changed[32:])

    def test_missing_or_ambiguous_ore_data_is_rejected(self):
        for raw in (b'no ore data', builder.STOCK + builder.STOCK):
            with self.assertRaises(ValueError):
                builder.patch_payload(raw)

    def test_steam_verify_removal_is_restored_without_disturbing_other_mods(self):
        original = 'set-exe Data\\ra3ep1_1.1.game\r\nadd-big VeteranAI.big\r\nadd-big Data\\StaticStream.big\r\n'
        path = Path(r'C:\Users\Example\.local\share\ra3-uprising-ore100k\Uprising-Ore100K-Retail-v2.big')
        fixed = registration(original, path)
        self.assertEqual(fixed, registration(fixed, path))
        self.assertEqual(original, fixed.replace('add-big ' + str(path) + '\r\n', ''))
        self.assertEqual(fixed, registration(original, path))

    def test_duplicate_registration_collapses_to_one_priority_entry(self):
        path = Path('Ore.big')
        raw = 'set-exe Data\\ra3ep1_1.1.game\nadd-big AI.big\nadd-big Ore.big\nadd-big Ore.big\n'
        fixed = registration(raw, path)
        self.assertEqual(1, fixed.count('add-big Ore.big'))
        self.assertEqual('add-big Ore.big', fixed.splitlines()[1])

    def test_unknown_game_version_is_not_overwritten(self):
        with self.assertRaises(ValueError):
            registration('set-exe Unknown.game\n', Path('Ore.big'))

    def test_actual_registration_recovers_reset_and_defers_active_game(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            override = root / 'Ore.big'
            override.write_bytes(b'known local override fixture')
            config = root / 'RA3EP1_english_1.1.SkuDef'
            original = b'set-exe Data\\ra3ep1_1.1.game\r\nadd-big AI.big\r\n'
            config.write_bytes(original)
            receipt = {'game': str(root), 'override': str(override),
                'override_sha256': hashlib.sha256(override.read_bytes()).hexdigest()}
            (root / 'build-receipt.json').write_text(json.dumps(receipt))
            with patch('ra3_auto.ore_disk.ROOT', root):
                guard = DiskOverride()
                self.assertIn('deferred', guard.ensure(game_running=True))
                self.assertEqual(original, config.read_bytes())
                self.assertEqual('registration restored', guard.ensure())
                fixed = config.read_bytes()
                self.assertEqual('registered', guard.ensure())
                config.write_bytes(original)  # Simulated Steam file verification.
                self.assertEqual('registration restored', guard.ensure())
                self.assertEqual(fixed, config.read_bytes())
                self.assertEqual(original, fixed.replace(('add-big ' + str(override) + '\r\n').encode(), b''))
                override.write_bytes(b'corrupt fixture')
                with self.assertRaises(ValueError):
                    guard.ensure()
                self.assertEqual(fixed, config.read_bytes())


if __name__ == '__main__':
    unittest.main()
