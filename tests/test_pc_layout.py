"""Regression checks for the public PC entry points after directory changes."""

import importlib
from pathlib import Path
import subprocess
import sys
import types

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("name,implementation,symbol", [
    ("pc_gamepad_ui", "gamepad_ui", "rc_payload"),
    ("pc_keyboard_ui", "keyboard_ui", "apply_key"),
    ("pc_gamepad_probe", "gamepad_probe", "main"),
    ("pc_hid_probe", "hid_probe", "main"),
    ("pc_altitude", "altitude", "AltitudeClient"),
])
def test_legacy_imports_use_packaged_implementation(monkeypatch, name, implementation, symbol):
    # Import compatibility needs no terminal; Windows may not have curses installed.
    if name == "pc_keyboard_ui":
        monkeypatch.setitem(sys.modules, "curses", types.ModuleType("curses"))
    old = importlib.import_module(name)
    new = importlib.import_module("pc." + implementation)
    assert getattr(old, symbol) is getattr(new, symbol)


@pytest.mark.parametrize("old,new", [
    ("pc_gamepad_ui.py", "pc.gamepad_ui"),
    ("pc_hid_probe.py", "pc.hid_probe"),
])
def test_legacy_and_module_cli_options_match(old, new):
    legacy = subprocess.run([sys.executable, old, "--help"], cwd=ROOT,
                            capture_output=True, text=True, check=True, timeout=10)
    packaged = subprocess.run([sys.executable, "-m", new, "--help"], cwd=ROOT,
                              capture_output=True, text=True, check=True, timeout=10)
    assert "usage:" in legacy.stdout and "usage:" in packaged.stdout
    assert legacy.stdout.split("options:", 1)[1] == packaged.stdout.split("options:", 1)[1]
