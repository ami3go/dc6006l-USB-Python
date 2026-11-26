"""Generate a square wave by switching the output ON/OFF.

Usage: python examples/square_wave.py /dev/ttyUSB0

Note: each switch is confirmed by a status readback, which takes a few
hundred milliseconds, so pulse widths are approximate minimums.
"""

import time

from _common import parse_args, safe_shutdown

from dc6006l import DC6006L, DC6006LError

V_HIGH = 5.0  # V
REPEATS = 10
ON_TIME = 0.5  # s
OFF_TIME = 0.8  # s


def main() -> None:
    args = parse_args(__doc__)
    with DC6006L(args.port) as psu:
        try:
            psu.output_off()
            psu.set_ovp(V_HIGH + 0.5)
            psu.set_voltage(V_HIGH)
            for n in range(REPEATS):
                s = psu.output_on()
                time.sleep(ON_TIME)
                print(f"{n}: ON  V={s.voltage} V I={s.current} A")
                s = psu.output_off()
                time.sleep(OFF_TIME)
                print(f"{n}: OFF V={s.voltage} V I={s.current} A")
        except DC6006LError as exc:
            print(f"ERROR: {exc}")
        finally:
            safe_shutdown(psu)


if __name__ == "__main__":
    main()
