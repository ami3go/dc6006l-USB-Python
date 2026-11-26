# Hardware-in-the-loop (HIL) runbook

**Status: NOT RUN.** This procedure has not been executed. Software tests
(`pytest`) use a simulated device and are **not** hardware qualification.

Run only with explicit authorisation, by an operator who can physically
disconnect the supply at any time.

## 0. Setup

* DC6006L powered from its own input supply, USB to host, latest driver
  checkout installed (`pip install .`).
* **No DUT.** Output terminals open (steps 1–4), then a resistive load
  rated ≥ 10 W, e.g. 100 Ω (steps 5–6).
* Independent calibrated DMM across the output terminals.
* Operator hand on the supply's front-panel output button / mains switch.
* Enable logging with `logging.basicConfig(level=logging.DEBUG)` (or run
  examples with `-v`) and save the log for evidence.

**Stop criteria (any step):** DMM reads > 1 V above the requested value,
any unexpected output ON, any exception not listed as expected, smoke/heat.
→ Press output OFF on the front panel, disconnect, record evidence.

## 1. Connection and status (output must stay OFF)

```python
from dc6006l import DC6006L
psu = DC6006L("<port>").open()
s = psu.get_status(); print(s)
```

Expected: `Status` with `output_on=False`; DMM ≈ 0 V. Record `raw`.
Compare `voltage_set`, `current_set`, `ovp`, `ocp` with the front panel.

## 2. Output OFF confirmation

`psu.output_off()` → returns, `output_on=False`, DMM ≈ 0 V.

## 3. Field-semantics confirmation (open output, output OFF)

Confirms the assumptions in docs/PROTOCOL.md (status-frame field meanings).

| Call | Front panel must show | Returned field |
|---|---|---|
| `set_ovp(5.5)` | OVP 5.50 V | `ovp == 5.50` |
| `set_ocp(0.2)` | OCP 0.200 A | `ocp == 0.200` |
| `set_voltage(3.3)` | Vset 3.30 V | `voltage_set == 3.30` |
| `set_current(0.1)` | Iset 0.100 A | `current_set == 0.100` |
| `set_voltage(0.7)` | Vset 0.70 V (historic bug value) | `voltage_set == 0.70` |

Any `VerificationError` here is a finding; record `.requested`/`.actual`.

## 4. Output ON, open terminals

`set_ovp(5.5)`, `set_voltage(3.3)`, `output_on()` → DMM 3.30 V ± 0.05 V,
returned `output_on=True`. Then `output_off()` → DMM ≈ 0 V.

## 5. Load test (100 Ω)

`set_ocp(0.2)`, `set_current(0.1)`, `set_voltage(5)`, `output_on()`.
Expected: CV mode (`mode == CV`), current ≈ 0.050 A (5 V / 100 Ω is below
the 0.1 A limit). Then `set_current(0.03)` → `mode == CC`, current ≈ 0.030 A,
DMM ≈ 3 V.
`output_off()`.

## 6. Protection trip

`set_ovp(5)`, `set_voltage(4)`, `output_on()`, then `set_ovp(3.5)` or raise
voltage to 4.5 V and lower OVP below it. Expected: device trips,
`error == DeviceError.OVER_VOLTAGE`, output OFF on DMM. Record frames.

## 7. Reporting and unplug

`start_reporting()`; `read_report()` ×10; record the frame interval.
Unplug USB during `read_report()` → `TransportError`, `is_open is False`.

## 8. Evidence

Attach: log files, raw frames, DMM photos/readings per step, firmware
version (front panel), hardware revision. Update docs/PROTOCOL.md items
from **[assumed]** to **[observed]** only with this evidence.
