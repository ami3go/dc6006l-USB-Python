# DC6006L serial protocol (reverse-engineered)

FNIRSI has not published a protocol specification. Everything below was
obtained by sniffing the serial line with a logic analyser (original author)
and from the behaviour of the original driver. Each item is marked:

* **[observed]** – seen on the wire / relied upon by the original driver that
  was used with real hardware;
* **[assumed]** – inferred, not confirmed by a controlled capture;
* **[unknown]** – open question.

## Link

* USB CDC / virtual COM port, 115200 baud, 8N1 **[observed]**.
* Commands: ASCII, terminated by CR LF (`\r\n`) **[observed]**.
* Device frames: ASCII digit fields, each followed by `A`; **no terminator**
  between frames **[observed]** (the original driver read back-to-back
  27-byte chunks and checked `A` positions).

## Commands

| Command | Meaning | Unit | Range used by driver | Implemented |
|---|---|---|---|---|
| `Vnnnn` | output voltage setpoint | 0.01 V | 0000–6000 | `set_voltage` |
| `Innnn` | output current limit | 1 mA | 0000–6000 | `set_current` |
| `Bnnnn` | over-voltage protection (OVP) | 0.01 V | 0020–6100 | `set_ovp` |
| `Dnnnn` | over-current protection (OCP) | 1 mA | 0000–6000 | `set_ocp` |
| `Ennnn` | over-power protection (OPP) | 0.1 W **[assumed]** | – | no |
| `Hnn` / `Mnn` / `Snn` | timer hours / minutes / seconds | – | – | no |
| `X` / `Y` | enable / disable timer | – | – | no |
| `N` | output ON (absolute, not a toggle) **[observed]** | – | – | `output_on` |
| `F` | output OFF (absolute, not a toggle) **[observed]** | – | – | `output_off` |
| `Q` | start periodic reporting; device first sends a status frame **[observed]** | – | – | `start_reporting`, `get_status` |
| `W` | stop periodic reporting | – | – | `stop_reporting`, `get_status` |

Numeric fields are exactly 4 decimal digits, zero-padded.

Range limits come from the original driver and the nominal 60 V / 6 A rating;
they are **not** confirmed for every hardware/firmware revision **[assumed]**.

## Report frame (27 bytes, periodic while reporting is on)

```
0199A 0700A 0139A 0A 029A 0A 0A 1A      (spaces for readability only)
VVVV  IIII  PPPP  x  TTT  m  e  o
```

| Field | Width | Meaning | Unit |
|---|---|---|---|
| V | 4 | measured output voltage | 0.01 V |
| I | 4 | measured output current | 1 mA |
| P | 4 | output power | 0.01 W (1.99 V × 0.700 A = 1.39 W) |
| x | 1 | **[unknown]**, exposed as `unknown_p1` | – |
| T | 3 | temperature | °C **[assumed]** |
| m | 1 | 0 = CV, 1 = CC | – |
| e | 1 | 0 = OK, 1 = OVP, 2 = OCP, 3 = over-time; other values **[unknown]** | – |
| o | 1 | output 0 = OFF, 1 = ON | – |

Examples **[observed]**:

```
0199A0700A0139A0A029A0A0A1A   output on
0000A0000A0000A0A029A0A0A0A   output off
0000A0000A0000A0A029A0A2A0A   short circuit (OCP)
0058A0098A0005A0A028A1A0A1A   current limit active (CC)
```

## Status frame (66 bytes, sent once after `Q`)

`KB` + the 27-byte report body + 37 bytes:

```
SSSSA CCCCA LLLLA KKKKA WWWWWA tA hhA mmA ssA
```

| Field | Width | Meaning (from original driver) | Unit |
|---|---|---|---|
| S | 4 | voltage setpoint | 0.01 V |
| C | 4 | current setpoint | 1 mA |
| L | 4 | OVP limit | 0.01 V |
| K | 4 | OCP limit | 1 mA |
| W | 5 | OPP limit | 0.01 W |
| t | 1 | timer enabled | 0/1 |
| hh, mm, ss | 2 each | timer | h, min, s |

The layout is **[observed]** (parsed by the original `get_status`). The
*meaning* of the setpoint/limit fields is the original author's
interpretation **[assumed]**; the driver relies on it for verification, so it
must be confirmed by the HIL runbook (`docs/HIL_RUNBOOK.md`, step 3).

The meaning of the `KB` prefix is **[unknown]**.

## How the driver uses the protocol

* **Status read** (`get_status`): `W`, then drop all received bytes, `Q`,
  wait for a `KB` status frame received after `Q`, then `W` again if
  reporting was off before. Retried up to `status_attempts` times (read-only,
  safe to retry).
* **Setpoint/protection**: write the command once, then perform a status
  read and compare the corresponding field exactly (same resolution). Never
  resent automatically.
* **Output**: write `N`/`F`, then a status read; resend up to
  `output_attempts` times (absolute commands, idempotent).
* At least 0.1 s between commands (the original driver always slept ≥ 0.1 s;
  pacing is kept as a precaution).

## Open questions

1. Does the device send any reply to `V`/`I`/`B`/`D`/`N`/`F`? The original
   driver read 10 or 27 bytes after them, which match the beginning of a
   report frame; the driver no longer reads command replies.
2. Report frame rate.
3. Meaning of field `x` and of `KB`.
4. Root cause of the reported "0.7 V applied as 7 V / 70 V" issue (README,
   13.04.2021): firmware parsing vs. line corruption. The driver detects such
   a mismatch via readback and switches the output off, but cannot prevent the
   device from briefly applying the wrong value.
5. Whether limits differ between hardware/firmware revisions.
6. Whether values written while the output is ON take effect immediately.
