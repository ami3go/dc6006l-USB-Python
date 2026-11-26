"""Print the full device status once. Does not change any setting or the output.

Usage: python examples/status_readout.py /dev/ttyUSB0
"""

from _common import parse_args

from dc6006l import DC6006L, DC6006LError


def main() -> None:
    args = parse_args(__doc__)
    with DC6006L(args.port) as psu:
        try:
            s = psu.get_status()
        except DC6006LError as exc:
            print(f"ERROR: {exc}")
            return
        error = s.error.name if s.error is not None else f"undocumented code {s.error_code}"
        print(f"Output      : {'ON' if s.output_on else 'OFF'} ({s.mode.name})")
        print(f"Measured    : {s.voltage} V  {s.current} A  {s.power} W")
        print(f"Setpoints   : {s.voltage_set} V  {s.current_set} A")
        print(f"Protection  : OVP {s.ovp} V  OCP {s.ocp} A  OPP {s.opp} W")
        print(f"Timer       : {'on' if s.timer_enabled else 'off'} "
              f"{s.timer_hours:02d}:{s.timer_minutes:02d}:{s.timer_seconds:02d}")
        print(f"Temperature : {s.temperature} C")
        print(f"Error       : {error}")


if __name__ == "__main__":
    main()
