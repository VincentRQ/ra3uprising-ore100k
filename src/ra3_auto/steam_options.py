"""Persist RA3/Uprising -win options when Steam is not writing localconfig.vdf."""

import argparse
import json
import os
import re
import shutil
import tempfile
import time
import winreg
from pathlib import Path

from ra3_auto.paths import DATA_ROOT, log_path
from ra3_auto.processes import is_process_running


APP_IDS = ("17480", "24800")
LOG_PATH = log_path("steam-options.log")
STATE_PATH = DATA_ROOT / "state.json"


def log(message):
    with LOG_PATH.open("a", encoding="utf-8") as stream:
        stream.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def load_state():
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"added_launch_options": []}


def save_state(state):
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, STATE_PATH)


def remember_added_options(app_ids):
    state = load_state()
    owned = set(state.get("added_launch_options", []))
    owned.update(app_ids)
    state["added_launch_options"] = sorted(owned)
    save_state(state)


def steam_running():
    return is_process_running("steam.exe")


def registry_value(key_path, name, default=None):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return default


def find_localconfig():
    steam_path = registry_value(r"Software\Valve\Steam", "SteamPath")
    active_user = registry_value(r"Software\Valve\Steam\ActiveProcess", "ActiveUser", 0)
    if not steam_path:
        return None
    steam_root = Path(steam_path)
    if active_user:
        candidate = steam_root / "userdata" / str(active_user) / "config" / "localconfig.vdf"
        if candidate.exists():
            return candidate
    candidates = list((steam_root / "userdata").glob("*/config/localconfig.vdf"))
    matching = []
    for candidate in candidates:
        try:
            sample = candidate.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if any(f'"{app_id}"' in sample for app_id in APP_IDS):
            matching.append(candidate)
    return max(matching, key=lambda path: path.stat().st_mtime) if matching else None


def block_bounds(lines, app_id):
    for index in range(len(lines) - 1):
        if lines[index].strip() != f'"{app_id}"' or lines[index + 1].strip() != "{":
            continue
        depth = 0
        for end in range(index + 1, len(lines)):
            stripped = lines[end].strip()
            if stripped == "{":
                depth += 1
            elif stripped == "}":
                depth -= 1
                if depth == 0:
                    return index + 1, end
    raise ValueError(f"Steam app block {app_id} was not found")


def ensure_win_option(text, app_id):
    lines = text.splitlines(keepends=True)
    start, end = block_bounds(lines, app_id)
    launch_pattern = re.compile(r'^(\s*)"LaunchOptions"\s+"(.*)"\s*$')
    for index in range(start + 1, end):
        match = launch_pattern.match(lines[index].rstrip("\r\n"))
        if not match:
            continue
        options = match.group(2).split()
        if any(option.casefold() == "-win" for option in options):
            return text, False
        options.append("-win")
        newline = "\r\n" if lines[index].endswith("\r\n") else "\n"
        lines[index] = f'{match.group(1)}"LaunchOptions"\t\t"{" ".join(options)}"{newline}'
        return "".join(lines), True

    indent = re.match(r"\s*", lines[start]).group(0) + "\t"
    newline = "\r\n" if any(line.endswith("\r\n") for line in lines[:10]) else "\n"
    lines.insert(start + 1, f'{indent}"LaunchOptions"\t\t"-win"{newline}')
    return "".join(lines), True


def remove_win_option(text, app_id):
    lines = text.splitlines(keepends=True)
    start, end = block_bounds(lines, app_id)
    launch_pattern = re.compile(r'^(\s*)"LaunchOptions"\s+"(.*)"\s*$')
    for index in range(start + 1, end):
        match = launch_pattern.match(lines[index].rstrip("\r\n"))
        if not match:
            continue
        options = match.group(2).split()
        retained = [option for option in options if option.casefold() != "-win"]
        if len(retained) == len(options):
            return text, False
        if retained:
            newline = "\r\n" if lines[index].endswith("\r\n") else "\n"
            lines[index] = (
                f'{match.group(1)}"LaunchOptions"\t\t"{" ".join(retained)}"{newline}'
            )
        else:
            del lines[index]
        return "".join(lines), True
    return text, False


def write_atomic(path, text):
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        dir=path.parent,
        prefix="localconfig.ra3-auto.",
        suffix=".tmp",
        delete=False,
    ) as stream:
        stream.write(text)
        temporary = Path(stream.name)
    os.replace(temporary, path)


def update_localconfig(path):
    original = path.read_text(encoding="utf-8")
    updated = original
    changed_apps = []
    for app_id in APP_IDS:
        try:
            updated, changed = ensure_win_option(updated, app_id)
        except ValueError:
            log(f"Steam app block {app_id} is not present; skipped")
            continue
        if changed:
            changed_apps.append(app_id)
    if not changed_apps:
        return False

    backup = path.with_name(path.name + ".ra3-auto-backup")
    if not backup.exists():
        shutil.copy2(path, backup)
        log(f"created backup {backup}")
    write_atomic(path, updated)
    remember_added_options(changed_apps)
    log(f"set -win for app ids {','.join(changed_apps)}")
    return True


def remove_owned_options(path):
    state = load_state()
    owned = [app_id for app_id in state.get("added_launch_options", []) if app_id in APP_IDS]
    if not owned:
        log("no installer-owned Steam launch options to remove")
        return False

    original = path.read_text(encoding="utf-8")
    updated = original
    removed = []
    for app_id in owned:
        try:
            updated, changed = remove_win_option(updated, app_id)
        except ValueError:
            continue
        if changed:
            removed.append(app_id)
    if updated != original:
        write_atomic(path, updated)
    state["added_launch_options"] = []
    save_state(state)
    log(f"removed installer-owned -win for app ids {','.join(removed) or 'none'}")
    return bool(removed)


def self_test():
    sample = (
        '"Software"\n{\n\t"Apps"\n\t{\n'
        '\t\t"17480"\n\t\t{\n\t\t\t"LaunchOptions"\t\t"-foo"\n\t\t}\n'
        '\t\t"24800"\n\t\t{\n\t\t}\n\t}\n}\n'
    )
    updated = sample
    for app_id in APP_IDS:
        updated, changed = ensure_win_option(updated, app_id)
        if not changed:
            return 1
    for app_id in APP_IDS:
        updated, changed = ensure_win_option(updated, app_id)
        if changed:
            return 1
        updated, removed = remove_win_option(updated, app_id)
        if not removed:
            return 1
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--remove-owned", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if args.once or args.remove_owned:
        if steam_running():
            log("Steam is running; localconfig.vdf was not changed")
            return 3
        path = find_localconfig()
        if not path:
            log("Steam localconfig.vdf was not found")
            return 2
        if args.remove_owned:
            remove_owned_options(path)
        else:
            update_localconfig(path)
        return 0

    log("Steam launch-options watcher started")
    while True:
        if not steam_running():
            path = find_localconfig()
            if path:
                try:
                    update_localconfig(path)
                except Exception as error:
                    log(f"update failed: {type(error).__name__}: {error}")
        time.sleep(5.0)


if __name__ == "__main__":
    raise SystemExit(main())
