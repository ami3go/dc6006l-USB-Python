"""Finding 15: examples compile and run against the fake device (no hardware)."""

import importlib
import os
import py_compile
import subprocess
import sys

import pytest

from dc6006l import DC6006L

EXAMPLES = os.path.join(os.path.dirname(__file__), "..", "examples")
SCRIPTS = sorted(f for f in os.listdir(EXAMPLES) if f.endswith(".py"))


@pytest.mark.parametrize("name", SCRIPTS)
def test_example_compiles(name):
    py_compile.compile(os.path.join(EXAMPLES, name), doraise=True)


@pytest.mark.parametrize("name", [s for s in SCRIPTS if not s.startswith("_")])
def test_example_help_runs(name):
    r = subprocess.run([sys.executable, os.path.join(EXAMPLES, name), "--help"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize(
    "name,overrides",
    [
        ("basic_usage", {}),
        ("square_wave", {"REPEATS": 2, "ON_TIME": 0, "OFF_TIME": 0}),
        ("voltage_ramp", {"CYCLES": 1, "STEP_DELAY": 0}),
    ],
)
def test_example_runs_against_fake(monkeypatch, capsys, dev, name, overrides):
    monkeypatch.syspath_prepend(EXAMPLES)
    mod = importlib.import_module(name)
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    for k, val in overrides.items():
        monkeypatch.setattr(mod, k, val)
    monkeypatch.setattr(
        mod,
        "DC6006L",
        lambda port: DC6006L(port, serial_factory=dev.serial_factory, min_command_interval=0, status_timeout=0.2),
    )
    monkeypatch.setattr(sys, "argv", [name, "FAKE"])
    mod.main()
    out = capsys.readouterr().out
    assert "ERROR" not in out
    assert "Output OFF confirmed" in out
    assert not dev.output
