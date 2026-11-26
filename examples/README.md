# Examples

Run from the repository root (or anywhere) with the serial port as argument:

```bash
pip install .
python examples/status_readout.py /dev/ttyUSB0     # Windows: COM5
```

Add `-v` to log the serial traffic.

| Script | What it does | Changes output? |
|---|---|---|
| `status_readout.py` | prints the full status once | no |
| `protection_setup.py` | sets OVP/OCP and 12 V / 1 A, leaves output OFF; shows handling of every exception | output OFF only |
| `basic_usage.py` | 5 V / 0.5 A with OVP, output ON for 1 s | yes |
| `square_wave.py` | toggles 5 V on/off 10 times | yes |
| `voltage_ramp.py` | ramps 2 V ↔ 10 V in 0.1 V steps | yes |
| `monitor.py` | prints periodic reports, restarts output if current drops to 0 (Ctrl+C to stop) | yes |

All scripts that switch the output on also switch it off on exit or error
(`safe_shutdown` in `_common.py`), and say so if OFF could not be confirmed.

⚠ Disconnect sensitive loads before trying them: see the safety warning in
the main README.
