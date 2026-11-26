"""Ramp the output voltage up and down between two levels.

Usage: python examples/voltage_ramp.py /dev/ttyUSB0
"""

import time
from decimal import Decimal

from _common import parse_args, safe_shutdown

from dc6006l import DC6006L, DC6006LError

V_LOW = Decimal("2.0")  # Decimal avoids accumulating float error
V_HIGH = Decimal("10.0")
STEP = Decimal("0.1")
CYCLES = 10
STEP_DELAY = 0.5  # s


def main() -> None:
    args = parse_args(__doc__)
    up = [V_LOW + STEP * k for k in range(int((V_HIGH - V_LOW) / STEP) + 1)]
    with DC6006L(args.port) as psu:
        try:
            psu.output_off()
            psu.set_ovp(V_HIGH + 1)
            psu.set_voltage(V_LOW)
            psu.output_on()
            for _ in range(CYCLES):
                for v in up + up[-2:0:-1]:
                    s = psu.set_voltage(v)
                    time.sleep(STEP_DELAY)
                    print(f"Vset={s.voltage_set} V  Vout={s.voltage} V  Iout={s.current} A")
        except DC6006LError as exc:
            print(f"ERROR: {exc}")
        finally:
            safe_shutdown(psu)


if __name__ == "__main__":
    main()
