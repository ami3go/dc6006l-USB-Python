"""Shared helpers for the examples (not part of the library)."""

import argparse
import logging


def parse_args(description: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("port", help='serial port, e.g. "COM5" or "/dev/ttyUSB0"')
    parser.add_argument("-v", "--verbose", action="store_true", help="log serial traffic")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING)
    return args


def safe_shutdown(psu) -> None:
    """Best-effort output OFF; reports (never hides) a failure to confirm."""
    if not psu.is_open:
        print("WARNING: connection lost - output state UNKNOWN, check the supply")
        return
    try:
        psu.output_off()
        print("Output OFF confirmed")
    except Exception as exc:
        print(f"WARNING: could not confirm output OFF ({exc}) - check the supply")
