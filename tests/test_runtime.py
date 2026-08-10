import ctypes
import os
import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from ra3_auto import edge_scroll, steam_options  # noqa: E402
from ra3_auto.processes import find_first_process, process_map  # noqa: E402


SAMPLE_VDF = (
    '"Software"\r\n{\r\n\t"Valve"\r\n\t{\r\n\t\t"Steam"\r\n\t\t{\r\n'
    '\t\t\t"apps"\r\n\t\t\t{\r\n'
    '\t\t\t\t"17480"\r\n\t\t\t\t{\r\n'
    '\t\t\t\t\t"LaunchOptions"\t\t"-foo"\r\n'
    '\t\t\t\t}\r\n'
    '\t\t\t\t"24800"\r\n\t\t\t\t{\r\n\t\t\t\t}\r\n'
    '\t\t\t}\r\n\t\t}\r\n\t}\r\n}\r\n'
)


class SteamOptionTests(unittest.TestCase):
    def test_add_is_idempotent_and_preserves_existing_options(self):
        updated, changed_base = steam_options.ensure_win_option(SAMPLE_VDF, "17480")
        updated, changed_uprising = steam_options.ensure_win_option(updated, "24800")
        self.assertTrue(changed_base)
        self.assertTrue(changed_uprising)
        self.assertIn('"LaunchOptions"\t\t"-foo -win"', updated)

        for app_id in steam_options.APP_IDS:
            same, changed = steam_options.ensure_win_option(updated, app_id)
            self.assertFalse(changed)
            self.assertEqual(updated, same)

    def test_remove_preserves_unrelated_options(self):
        updated, _ = steam_options.ensure_win_option(SAMPLE_VDF, "17480")
        updated, removed = steam_options.remove_win_option(updated, "17480")
        self.assertTrue(removed)
        self.assertIn('"LaunchOptions"\t\t"-foo"', updated)

    def test_remove_deletes_empty_launch_option(self):
        updated, _ = steam_options.ensure_win_option(SAMPLE_VDF, "24800")
        updated, removed = steam_options.remove_win_option(updated, "24800")
        self.assertTrue(removed)
        start, end = steam_options.block_bounds(updated.splitlines(keepends=True), "24800")
        block = "".join(updated.splitlines(keepends=True)[start:end])
        self.assertNotIn("LaunchOptions", block)

    def test_missing_app_block_is_explicit(self):
        with self.assertRaises(ValueError):
            steam_options.ensure_win_option(SAMPLE_VDF, "99999")


class WindowsRuntimeTests(unittest.TestCase):
    def test_input_layout_matches_win32(self):
        expected = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
        self.assertEqual(expected, ctypes.sizeof(edge_scroll.INPUT))

    def test_toolhelp_snapshot_finds_current_python(self):
        executable_name = Path(sys.executable).name.casefold()
        snapshot = process_map()
        self.assertIn(executable_name, snapshot)
        self.assertIn(os.getpid(), snapshot[executable_name])
        pid, _ = find_first_process([executable_name])
        self.assertIsNotNone(pid)


if __name__ == "__main__":
    unittest.main()
