"""Command encoding and frame scanning/parsing for the DC6006L.

The protocol is reverse-engineered (see docs/PROTOCOL.md). Only the commands
and frame layouts already used by the original driver are implemented.

Commands are ASCII, terminated with CR LF. Device frames are ASCII digit
fields each followed by ``A``, without any terminator:

* report frame (27 bytes): ``VVVVA IIIIA PPPPA xA TTTA mA eA oA``
* status frame (66 bytes): ``KB`` + report body (27) +
  ``SSSSA CCCCA LLLLA KKKKA WWWWWA tA hhA mmA ssA`` (37)

(spaces added for readability only).
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple, Union

from . import validation as v
from .exceptions import ProtocolError
from .models import Report, RegulationMode, Status

TERMINATOR = b"\r\n"

CMD_OUTPUT_ON = "N"
CMD_OUTPUT_OFF = "F"
CMD_REPORT_START = "Q"
CMD_REPORT_STOP = "W"


def _encode(prefix: str, units: int, quantity: v.Quantity) -> bytes:
    # Defensive re-check: callers must pass already validated units.
    if not isinstance(units, int) or isinstance(units, bool):
        raise TypeError("units must be int")
    if not quantity.min_units <= units <= quantity.max_units:
        raise ValueError(f"{quantity.name} units {units} out of range")
    field = f"{units:0{quantity.digits}d}"
    if len(field) != quantity.digits:  # pragma: no cover - guarded by range
        raise ValueError("field width overflow")
    return f"{prefix}{field}".encode("ascii") + TERMINATOR


def encode_voltage(units: int) -> bytes:
    """``Vnnnn`` - output voltage setpoint in 0.01 V."""
    return _encode("V", units, v.VOLTAGE)


def encode_current(units: int) -> bytes:
    """``Innnn`` - output current limit in 1 mA."""
    return _encode("I", units, v.CURRENT)


def encode_ovp(units: int) -> bytes:
    """``Bnnnn`` - over-voltage protection in 0.01 V."""
    return _encode("B", units, v.OVP)


def encode_ocp(units: int) -> bytes:
    """``Dnnnn`` - over-current protection in 1 mA."""
    return _encode("D", units, v.OCP)


def encode_simple(cmd: str) -> bytes:
    """Encode a one-letter command (N, F, Q, W)."""
    if cmd not in (CMD_OUTPUT_ON, CMD_OUTPUT_OFF, CMD_REPORT_START, CMD_REPORT_STOP):
        raise ValueError(f"unsupported command {cmd!r}")
    return cmd.encode("ascii") + TERMINATOR


# --------------------------------------------------------------------------
# Frame grammar
# --------------------------------------------------------------------------

_REPORT_BODY = rb"(\d{4})A(\d{4})A(\d{4})A(\d)A(\d{3})A(\d)A(\d)A(\d)A"
_STATUS_EXT = rb"(\d{4})A(\d{4})A(\d{4})A(\d{4})A(\d{5})A(\d)A(\d{2})A(\d{2})A(\d{2})A"

STATUS_PREFIX = b"KB"
REPORT_LEN = 27
STATUS_LEN = 66

_REPORT_RE = re.compile(_REPORT_BODY)
_STATUS_RE = re.compile(re.escape(STATUS_PREFIX) + _REPORT_BODY + _STATUS_EXT)

# Character layout of a status frame: "K", "B", then "d" (digit) or "A".
_REPORT_WIDTHS = (4, 4, 4, 1, 3, 1, 1, 1)
_STATUS_EXT_WIDTHS = (4, 4, 4, 4, 5, 1, 2, 2, 2)
_STATUS_LAYOUT = "KB" + "".join("d" * w + "A" for w in _REPORT_WIDTHS + _STATUS_EXT_WIDTHS)
assert len(_STATUS_LAYOUT) == STATUS_LEN


def _could_be_status_prefix(data: bytes) -> bool:
    """True if ``data`` (starting at "KB") is consistent with a status frame so far."""
    for byte, kind in zip(data, _STATUS_LAYOUT):
        if kind == "d":
            if not 0x30 <= byte <= 0x39:
                return False
        elif byte != ord(kind):
            return False
    return True

Frame = Union[Report, Status]


def _report_fields(g: Tuple[bytes, ...], raw: bytes) -> dict:
    mode_raw, out_raw = int(g[5]), int(g[7])
    try:
        mode = RegulationMode(mode_raw)
    except ValueError:
        raise ProtocolError(f"unknown CV/CC value {mode_raw}", raw) from None
    if out_raw not in (0, 1):
        raise ProtocolError(f"unknown output state value {out_raw}", raw)
    return dict(
        voltage=v.from_units(int(g[0]), v.VOLTAGE),
        current=v.from_units(int(g[1]), v.CURRENT),
        power=int(g[2]) * v.VOLTAGE.resolution,  # 0.01 W
        unknown_p1=int(g[3]),
        temperature=int(g[4]),
        mode=mode,
        error_code=int(g[6]),
        output_on=out_raw == 1,
        raw=raw,
    )


def parse_report(raw: bytes) -> Report:
    """Parse exactly one 27-byte report frame."""
    m = _REPORT_RE.fullmatch(raw)
    if not m:
        raise ProtocolError("not a valid report frame", raw)
    return Report(**_report_fields(m.groups(), raw))


def parse_status(raw: bytes) -> Status:
    """Parse exactly one 66-byte status frame."""
    m = _STATUS_RE.fullmatch(raw)
    if not m:
        raise ProtocolError("not a valid status frame", raw)
    g = m.groups()
    fields = _report_fields(g[:8], raw)
    timer_en = int(g[13])
    if timer_en not in (0, 1):
        raise ProtocolError(f"unknown timer-enable value {timer_en}", raw)
    hh, mm, ss = int(g[14]), int(g[15]), int(g[16])
    if mm > 59 or ss > 59:
        raise ProtocolError(f"invalid timer value {hh:02d}:{mm:02d}:{ss:02d}", raw)
    return Status(
        **fields,
        voltage_set=v.from_units(int(g[8]), v.VOLTAGE),
        current_set=v.from_units(int(g[9]), v.CURRENT),
        ovp=v.from_units(int(g[10]), v.VOLTAGE),
        ocp=v.from_units(int(g[11]), v.CURRENT),
        opp=int(g[12]) * v.VOLTAGE.resolution,  # 0.01 W
        timer_enabled=timer_en == 1,
        timer_hours=hh,
        timer_minutes=mm,
        timer_seconds=ss,
    )


class FrameScanner:
    """Incremental scanner that extracts frames from a byte stream.

    The device sends frames back-to-back with no terminator, and USB may
    deliver them in arbitrary fragments. :meth:`feed` accumulates bytes and
    returns every complete frame found, in order. Bytes that cannot belong to
    any frame are dropped and counted in :attr:`discarded`.

    Frames that match the grammar but contain invalid values are returned as
    :class:`ProtocolError` instances (not raised) so one bad frame does not
    hide later good ones.
    """

    MAX_BUFFER = 4 * STATUS_LEN

    def __init__(self) -> None:
        self._buf = bytearray()
        self.discarded = 0

    def reset(self) -> None:
        """Drop any partial frame."""
        self.discarded += len(self._buf)
        self._buf.clear()

    @property
    def pending(self) -> int:
        return len(self._buf)

    def feed(self, data: bytes) -> List[Union[Frame, ProtocolError]]:
        self._buf += data
        out: List[Union[Frame, ProtocolError]] = []
        while True:
            item = self._next()
            if item is None:
                break
            out.append(item)
        if len(self._buf) > self.MAX_BUFFER:
            drop = len(self._buf) - self.MAX_BUFFER
            del self._buf[:drop]
            self.discarded += drop
        return out

    def _next(self) -> Optional[Union[Frame, ProtocolError]]:
        buf = bytes(self._buf)
        kb = buf.find(STATUS_PREFIX)
        rm = _REPORT_RE.search(buf)
        # A status frame contains a report body at offset 2: if a status
        # prefix precedes the first report match, the status frame wins, and
        # we must wait for it to complete instead of emitting its inner body.
        if kb != -1 and (rm is None or kb <= rm.start()):
            sm = _STATUS_RE.match(buf, kb)
            if sm:
                return self._take(kb, sm.end(), parse_status)
            if len(buf) - kb < STATUS_LEN and _could_be_status_prefix(buf[kb:]):
                # Possibly incomplete status frame: keep it, drop what precedes.
                self._drop(kb)
                return None
            # "KB" followed by garbage: skip the prefix and rescan.
            self._drop(kb + len(STATUS_PREFIX))
            return self._next()
        if rm is None:
            # Keep the tail that could still start a frame.
            keep = REPORT_LEN - 1
            if len(buf) > keep:
                self._drop(len(buf) - keep)
            return None
        return self._take(rm.start(), rm.end(), parse_report)

    def _drop(self, n: int) -> None:
        if n > 0:
            del self._buf[:n]
            self.discarded += n

    def _take(self, start: int, end: int, parser) -> Union[Frame, ProtocolError]:
        self._drop(start)
        raw = bytes(self._buf[: end - start])
        del self._buf[: end - start]
        try:
            return parser(raw)
        except ProtocolError as exc:
            return exc
