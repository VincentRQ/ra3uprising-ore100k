"""Shared product constants and per-user data paths."""

import os
from pathlib import Path


APP_NAME = "RA3 Auto Enhance"
TASK_NAME = APP_NAME
PROCESS_NAMES = ("ra3_1.13.game", "RA3_1.12.game", "ra3ep1_1.1.game")
PROCESS_NAMES_ARGUMENT = ",".join(PROCESS_NAMES)
DATA_ROOT = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "RA3AutoEnhance"


def log_path(name):
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    return DATA_ROOT / name
