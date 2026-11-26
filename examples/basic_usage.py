"""Configure protection, set 5 V / 0.5 A, switch on, print status, switch off.

Usage: python examples/basic_usage.py /dev/ttyUSB0
"""

import time

from _common import parse_args, safe_shutdown

from dc6006l import DC6006L, DC6006LError


def main() -> None:
    args = parse_args(__doc__)
    with DC6006L(args.port) as psu:
        try:
            psu.output_off()  # start from a confirmed safe state
            psu.set_ovp(6.0)  # protection first, setpoints second
            psu.set_ocp(0.6)
            psu.set_voltage(5.0)
            psu.set_current(0.5)
            psu.output_on()
            time.sleep(1)
            s = psu.get_status()
            print(f"Vout={s.voltage} V  Iout={s.current} A  Pout={s.power} W  mode={s.mode.name}")
        except DC6006LError as exc:
            print(f"ERROR: {exc}")
        finally:
            safe_shutdown(psu)


if __name__ == "__main__":
    main()
