# dc6006l – Python driver for the FNIRSI DC6006L power supply

Control the affordable FNIRSI DC6006L programmable power supply through its
front USB port.
Power supply link: http://www.fnirsi.cn/productinfo/556155.html

FNIRSI did not publish the serial protocol; this library was created by
sniffing the serial communication with a logic analyser. See
[docs/PROTOCOL.md](docs/PROTOCOL.md) for what is known, what is assumed, and
the open questions.

**When you repost or share any information from this page please attach a
reference to this page.**

## ⚠ Safety warning

The firmware is immature. On 13.04.2021 a request for 0.7 V was observed to
be applied as 7 V or 70 V. The root cause is unknown.

* **Always configure over-voltage protection** (`set_ovp`) before switching
  the output on, and set voltage while the output is OFF.
* The driver reads back every setting and raises an error if the device
  reports a different value; on a mismatch with the output ON it switches the
  output OFF. It cannot stop the device from briefly applying a wrong value.
* Use the driver only where an unexpected voltage cannot cause harm, or add
  independent hardware protection.

## Installation

Python ≥ 3.9. The only runtime dependency is `pyserial`.

```bash
pip install .                 # from a checkout
pip install ".[dev]"          # plus pytest and build
```

## Quick start

```python
from dc6006l import DC6006L, list_ports

print(list_ports())

with DC6006L("/dev/ttyUSB0") as psu:          # or "COM5" on Windows
    psu.output_off()
    psu.set_ovp(6.0)
    psu.set_voltage(5.0)
    psu.set_current(0.5)
    psu.output_on()
    status = psu.get_status()
    print(status.voltage, status.current, status.mode.name)
    psu.output_off()
```

More in [examples/](examples/README.md) – status readout, protection setup
with full error handling, square wave, voltage ramp and monitoring. Run them
as `python examples/status_readout.py /dev/ttyUSB0`.

## API

All values are in volts, amperes, watts, °C. Inputs may be `int`, `float` or
`Decimal`; returned values are `Decimal`. Inputs are validated **before** any
serial I/O: out-of-range values, values finer than the resolution, `bool`,
strings, NaN and infinity raise `ValidationError`. Nothing is ever clamped or
rounded.

| Method | Range / resolution | Returns |
|---|---|---|
| `DC6006L(port, **options)` | see docstring for timeouts/retries | – |
| `open()` / `close()` / `with DC6006L(...)` | idempotent; `close()` never raises | `self` / `None` |
| `get_status()` | – | `Status` |
| `set_voltage(v)` | 0 – 60 V, 0.01 V | `Status` (verified) |
| `set_current(a)` | 0 – 6 A, 0.001 A | `Status` (verified) |
| `set_ovp(v)` | 0.2 – 61 V, 0.01 V | `Status` (verified) |
| `set_ocp(a)` | 0 – 6 A, 0.001 A | `Status` (verified) |
| `output_on()` / `output_off()` | – | `Status` (confirmed) |
| `start_reporting()` / `stop_reporting()` | – | `None` |
| `read_report(timeout=1.0)` | requires reporting | `Report` (fresh) |
| `list_ports()` | – | `list[str]` |

Every setter and output command is confirmed by a **fresh** status frame
requested after the command. Methods either return the confirmed state or
raise – they never return `True`/`False`/`None`.

`Report` fields: `voltage`, `current`, `power`, `temperature`, `mode`
(`RegulationMode.CV`/`CC`), `error_code`, `error` (`DeviceError` or `None`
if undocumented), `output_on`, `unknown_p1`, `raw`.
`Status` adds `voltage_set`, `current_set`, `ovp`, `ocp`, `opp`,
`timer_enabled`, `timer_hours`, `timer_minutes`, `timer_seconds`.

### Exceptions

All derive from `DC6006LError`.

| Exception | Meaning |
|---|---|
| `ValidationError` (also `ValueError`) | bad input; nothing was sent |
| `PortNotFoundError` | port does not exist |
| `NotConnectedError` | used before `open()` / after `close()` |
| `TransportError` | serial I/O failed; the connection is closed |
| `ResponseTimeoutError` | no valid frame in time |
| `ProtocolError` | only malformed frames received |
| `VerificationError` | device reads back a different value (`.requested`, `.actual`, `.status`, `.output_disabled`) |
| `IndeterminateError` | command sent, effect unknown (readback failed); not resent |
| `OutputStateError` | ON/OFF not confirmed; `.last_status is None` means state UNKNOWN |
| `ReportingError` | `read_report()` without `start_reporting()` |

Logging uses the standard `logging` module (logger `dc6006l`); set it to
`DEBUG` to see serial traffic.

### Thread safety

One `DC6006L` object may be shared between threads; each public call is an
atomic transaction on the port. Do not open the same port from two objects.

## Migrating from `src/dc6006l_class.py`

The old module was removed; it could never confirm protection settings and
could report output OFF from stale data.

| Old | New |
|---|---|
| `import src.dc6006l_class as ps; ps.dc6006l_class()` + `init(port)` | `from dc6006l import DC6006L; DC6006L(port).open()` |
| `init()` returns `False` | `open()` raises `PortNotFoundError` / `TransportError` |
| `set_v_out(v)` / `set_i_out(a)` | `set_voltage(v)` / `set_current(a)` |
| `set_volt_protect(v)` / `set_current_protect(a)` | `set_ovp(v)` / `set_ocp(a)` |
| `output_enable()` / `output_disable()` | `output_on()` / `output_off()` |
| `get_status()` dict, `get_status("v_out")` | `get_status().voltage` etc. |
| `get_state()` dict (`Vout`, `Output`, …) | `start_reporting()` + `read_report()` |
| `enable_state_reporting()` / `disable_state_reporting()` | `start_reporting()` / `stop_reporting()` |
| out-of-range values clamped | `ValidationError` |

## Development

```bash
pip install -e ".[dev]"
pytest
python -m build
```

Tests use a simulated device (`tests/fake_device.py`); no hardware needed.
Hardware validation follows [docs/HIL_RUNBOOK.md](docs/HIL_RUNBOOK.md).
