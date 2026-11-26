"""Configure OVP/OCP, then set the output, handling every failure explicitly.

Shows how to react to each driver exception when a wrong setting must never
reach the load.

Usage: python examples/protection_setup.py /dev/ttyUSB0
"""

from _common import parse_args, safe_shutdown

from dc6006l import (
    DC6006L,
    DC6006LError,
    IndeterminateError,
    OutputStateError,
    ValidationError,
    VerificationError,
)

OVP = 13.0  # V  - protection a little above the working voltage
OCP = 1.1  # A
VOLTAGE = 12.0  # V
CURRENT = 1.0  # A


def main() -> None:
    args = parse_args(__doc__)
    with DC6006L(args.port) as psu:
        try:
            psu.output_off()  # never configure with the output live
            psu.set_ovp(OVP)
            psu.set_ocp(OCP)
            psu.set_voltage(VOLTAGE)
            psu.set_current(CURRENT)
            s = psu.get_status()
            print(f"Verified: OVP {s.ovp} V, OCP {s.ocp} A, {s.voltage_set} V / {s.current_set} A")
            # Output deliberately left OFF: switch it on when the load is ready.
        except ValidationError as exc:
            print(f"Rejected before sending anything: {exc}")
        except VerificationError as exc:
            print(f"Device applied a different value: requested {exc.requested}, got {exc.actual}"
                  + (" - output was switched OFF" if exc.output_disabled else ""))
        except IndeterminateError as exc:
            print(f"Command {exc.command!r} sent but not confirmed - device state unknown: {exc}")
        except OutputStateError as exc:
            state = "UNKNOWN" if exc.last_status is None else ("ON" if exc.last_status.output_on else "OFF")
            print(f"Output could not be confirmed OFF (state {state}) - check the supply")
        except DC6006LError as exc:
            print(f"ERROR: {exc}")
        finally:
            safe_shutdown(psu)


if __name__ == "__main__":
    main()
