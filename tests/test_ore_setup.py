import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from ra3_auto import ore_setup, ore_disk


class OreSetupTests(unittest.TestCase):
    def test_uninstall_removes_only_owned_line_and_disables_repair(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);override=root/'Ore.big';override.write_bytes(b'local fixture')
            config=root/'RA3EP1_english_1.1.SkuDef'
            original='set-exe Data\\ra3ep1_1.1.game\r\nadd-big AI.big\r\n'
            config.write_bytes(ore_disk.registration(original,override).encode())
            receipt={'game':str(root),'override':str(override),'override_sha256':hashlib.sha256(override.read_bytes()).hexdigest()}
            (root/'build-receipt.json').write_text(json.dumps(receipt))
            with patch.object(ore_disk,'ROOT',root),patch.object(ore_setup,'ROOT',root),patch.object(ore_setup,'find_first_process',return_value=(None,None)):
                ore_setup.uninstall_registration(ore_disk.DiskOverride())
            self.assertEqual(original.encode(),config.read_bytes())
            self.assertFalse((root/'build-receipt.json').exists())
            self.assertTrue((root/'uninstalled-build-receipt.json').exists())
            self.assertEqual(b'local fixture',override.read_bytes())

    def test_uninstall_never_changes_configuration_during_a_match(self):
        with patch.object(ore_setup,'find_first_process',return_value=(1,'ra3ep1_1.1.game')):
            with self.assertRaises(RuntimeError):ore_setup.uninstall_registration(None)
