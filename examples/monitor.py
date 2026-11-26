"""Print periodic reports; restart the output if the measured current drops to 0.

Usage: python examples/monitor.py /dev/ttyUSB0
Stop with Ctrl+C.
"""

import time

from _common import parse_args, safe_shutdown

from dc6006l import DC6006L, DC6006LError, ResponseTimeoutError


def main() -> None:
    args = parse_args(__doc__)
    with DC6006L(args.port) as psu:
        try:
            psu.output_off()
            psu.set_ovp(2.5)
            psu.set_voltage(2.0)
            psu.output_on()
            psu.start_reporting()
            while True:
                try:
                    r = psu.read_report(timeout=2.0)
                except ResponseTimeoutError:
                    print("no report received - state unknown")
                    continue
                print(f"V={r.voltage} V  I={r.current} A  output={'ON' if r.output_on else 'OFF'}")
                if r.output_on and r.current == 0:
                    print("current is 0 - restarting output")
                    psu.output_off()
                    time.sleep(5)
                    psu.output_on()
        except KeyboardInterrupt:
            pass
        except DC6006LError as exc:
            print(f"ERROR: {exc}")
        finally:
            safe_shutdown(psu)


if __name__ == "__main__":
    main()
