"""High-level DC6006L driver."""

from __future__ import annotations

import logging
import time
from decimal import Decimal
from typing import Any, Optional

from . import protocol as p
from . import validation as v
from .exceptions import (
    DC6006LError,
    IndeterminateError,
    OutputStateError,
    ProtocolError,
    ReportingError,
    ResponseTimeoutError,
    VerificationError,
)
from .models import Report, Status
from .transport import SerialFactory, SerialTransport

log = logging.getLogger(__name__)


class DC6006L:
    """Driver for the FNIRSI DC6006L power supply over its USB serial port.

    Every operation that changes the device is confirmed by reading back a
    fresh full status frame requested *after* the command was written.
    Operations either return the confirmed :class:`Status` or raise; they
    never return ``True``/``False``/``None``.

    Usage::

        with DC6006L("/dev/ttyUSB0") as psu:
            psu.output_off()
            psu.set_ovp(6)
            psu.set_voltage(5)
            psu.set_current(0.5)
            psu.output_on()

    Thread safety: all public methods may be called from several threads;
    each runs as one atomic transaction on the serial port.

    :param port: serial device, e.g. ``"COM5"`` or ``"/dev/ttyUSB0"``.
    :param status_timeout: seconds to wait for a status frame per request.
    :param status_attempts: status requests (``W``, ``Q``) per readback.
        Status requests do not change device settings, so retrying is safe.
    :param output_attempts: how many times ``N``/``F`` is sent before
        :class:`OutputStateError` is raised. These commands set an absolute
        state (they are not toggles), so resending them is idempotent.
    :param disable_output_on_mismatch: if a setpoint or protection readback
        differs from the request while the output is ON, switch the output
        OFF before raising :class:`VerificationError` (fail-safe).
    :param min_command_interval: minimum seconds between two commands.
    :param serial_factory: for tests; called as ``factory(port, **kwargs)``
        instead of :class:`serial.Serial`. Skips the port-exists check.
    """

    def __init__(
        self,
        port: str,
        *,
        status_timeout: float = 1.0,
        status_attempts: int = 3,
        output_attempts: int = 3,
        disable_output_on_mismatch: bool = True,
        min_command_interval: float = 0.1,
        read_timeout: float = 0.02,
        serial_factory: Optional[SerialFactory] = None,
    ) -> None:
        if status_attempts < 1 or output_attempts < 1:
            raise ValueError("attempt counts must be >= 1")
        self._t = SerialTransport(
            port,
            serial_factory=serial_factory,
            read_timeout=read_timeout,
            min_command_interval=min_command_interval,
        )
        self._status_timeout = status_timeout
        self._status_attempts = status_attempts
        self._output_attempts = output_attempts
        self._disable_on_mismatch = disable_output_on_mismatch
        self._reporting = False

    # -- lifecycle --------------------------------------------------------

    @property
    def port(self) -> str:
        return self._t.port

    @property
    def is_open(self) -> bool:
        return self._t.is_open

    @property
    def reporting(self) -> bool:
        """Whether periodic reporting was enabled via :meth:`start_reporting`."""
        return self._reporting

    def open(self) -> "DC6006L":
        """Open the port and put reporting in a known (stopped) state.

        Idempotent. Raises :class:`PortNotFoundError` or
        :class:`TransportError`. Does not change any output setting.
        """
        if self._t.is_open:
            return self
        self._t.open()
        with self._t.transaction():
            self._t.write(p.encode_simple(p.CMD_REPORT_STOP), discard_input_first=True)
            self._reporting = False
        return self

    def close(self) -> None:
        """Close the port. Safe to call before ``open()`` and repeatedly.

        Does not switch the output off; call :meth:`output_off` first if
        required.
        """
        self._t.close()
        self._reporting = False

    def __enter__(self) -> "DC6006L":
        return self.open()

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- status -----------------------------------------------------------

    def get_status(self) -> Status:
        """Request and return a fresh full status frame.

        Raises :class:`ResponseTimeoutError` if no valid frame arrives, or
        :class:`ProtocolError` if only invalid frames arrive.
        """
        with self._t.transaction():
            return self._read_status()

    def _read_status(self) -> Status:
        last_err: Optional[ProtocolError] = None
        try:
            for attempt in range(1, self._status_attempts + 1):
                # The device sends the "KB" status frame when reporting is
                # (re)started; stop it first so Q produces a fresh frame.
                self._t.write(p.encode_simple(p.CMD_REPORT_STOP))
                self._t.write(p.encode_simple(p.CMD_REPORT_START), discard_input_first=True)
                deadline = time.monotonic() + self._status_timeout
                while time.monotonic() < deadline:
                    for frame in self._t.read_frames(deadline):
                        if isinstance(frame, Status):
                            return frame
                        if isinstance(frame, ProtocolError) and frame.raw and frame.raw.startswith(
                            p.STATUS_PREFIX
                        ):
                            last_err = frame
                log.debug("no status frame (attempt %d/%d)", attempt, self._status_attempts)
        finally:
            if not self._reporting and self._t.is_open:
                # Restore the caller's reporting state.
                self._t.write(p.encode_simple(p.CMD_REPORT_STOP))
        if last_err is not None:
            raise ProtocolError(f"only invalid status frames received: {last_err}", last_err.raw)
        raise ResponseTimeoutError(
            f"no status frame within {self._status_timeout}s x {self._status_attempts} attempts"
        )

    # -- setpoints and protection ------------------------------------------

    def set_voltage(self, volts: v.Number) -> Status:
        """Set the output voltage setpoint (V, 0.01 V resolution, 0..60 V).

        Returns the confirmed status. Raises :class:`ValidationError` before
        any I/O for invalid input, :class:`VerificationError` if the device
        reads back a different setpoint, :class:`IndeterminateError` if the
        readback failed (the command is not resent).
        """
        units = v.to_units(volts, v.VOLTAGE)
        return self._apply(p.encode_voltage(units), "voltage_set", v.from_units(units, v.VOLTAGE), v.VOLTAGE)

    def set_current(self, amps: v.Number) -> Status:
        """Set the output current limit (A, 0.001 A resolution, 0..6 A)."""
        units = v.to_units(amps, v.CURRENT)
        return self._apply(p.encode_current(units), "current_set", v.from_units(units, v.CURRENT), v.CURRENT)

    def set_ovp(self, volts: v.Number) -> Status:
        """Set over-voltage protection (V, 0.01 V resolution, 0.2..61 V)."""
        units = v.to_units(volts, v.OVP)
        return self._apply(p.encode_ovp(units), "ovp", v.from_units(units, v.OVP), v.OVP)

    def set_ocp(self, amps: v.Number) -> Status:
        """Set over-current protection (A, 0.001 A resolution, 0..6 A)."""
        units = v.to_units(amps, v.OCP)
        return self._apply(p.encode_ocp(units), "ocp", v.from_units(units, v.OCP), v.OCP)

    def _apply(self, cmd: bytes, field: str, expected: Decimal, quantity: v.Quantity) -> Status:
        name = cmd[:1].decode()
        with self._t.transaction():
            self._t.write(cmd, discard_input_first=True)
            try:
                status = self._read_status()
            except (ResponseTimeoutError, ProtocolError) as exc:
                raise IndeterminateError(
                    f"{name} command sent but the {quantity.name} could not be read back ({exc}); "
                    "device state is unknown and the command was not resent",
                    command=name,
                ) from exc
            actual = getattr(status, field)
            if actual == expected:
                return status
            disabled = False
            if self._disable_on_mismatch and status.output_on:
                disabled = self._failsafe_off()
            raise VerificationError(
                f"{quantity.name} readback mismatch: requested {expected} {quantity.unit}, "
                f"device reports {actual} {quantity.unit}"
                + ("; output switched OFF" if disabled else ""),
                parameter=field,
                requested=expected,
                actual=actual,
                status=status,
                output_disabled=disabled,
            )

    def _failsafe_off(self) -> bool:
        try:
            self._set_output(False)
            return True
        except DC6006LError as exc:
            log.error("fail-safe output OFF failed: %s", exc)
            return False

    # -- output -------------------------------------------------------------

    def output_on(self) -> Status:
        """Switch the output ON and confirm it from a fresh status frame.

        Raises :class:`OutputStateError` if ON cannot be confirmed; its
        ``last_status`` is ``None`` when the state is unknown.
        """
        with self._t.transaction():
            return self._set_output(True)

    def output_off(self) -> Status:
        """Switch the output OFF and confirm it from a fresh status frame."""
        with self._t.transaction():
            return self._set_output(False)

    def _set_output(self, on: bool) -> Status:
        cmd = p.encode_simple(p.CMD_OUTPUT_ON if on else p.CMD_OUTPUT_OFF)
        last: Optional[Status] = None
        reason = ""
        for attempt in range(1, self._output_attempts + 1):
            self._t.write(cmd, discard_input_first=True)
            try:
                last = self._read_status()
            except (ResponseTimeoutError, ProtocolError) as exc:
                last, reason = None, str(exc)
                continue
            if last.output_on == on:
                return last
            reason = f"device reports output {'ON' if last.output_on else 'OFF'} (error code {last.error_code})"
            log.warning("output %s not confirmed (attempt %d): %s", "ON" if on else "OFF", attempt, reason)
        state = "UNKNOWN" if last is None else ("ON" if last.output_on else "OFF")
        raise OutputStateError(
            f"could not confirm output {'ON' if on else 'OFF'} after {self._output_attempts} attempts; "
            f"output state is {state}: {reason}",
            requested_on=on,
            last_status=last,
        )

    # -- periodic reporting -------------------------------------------------

    def start_reporting(self) -> None:
        """Enable periodic report frames (``Q``)."""
        with self._t.transaction():
            self._t.write(p.encode_simple(p.CMD_REPORT_START), discard_input_first=True)
            self._reporting = True

    def stop_reporting(self) -> None:
        """Disable periodic report frames (``W``)."""
        with self._t.transaction():
            self._t.write(p.encode_simple(p.CMD_REPORT_STOP))
            self._reporting = False

    def read_report(self, timeout: float = 1.0) -> Report:
        """Return the next report frame received after this call.

        Requires :meth:`start_reporting`. Frames buffered before the call are
        discarded, so the result is never stale. Raises
        :class:`ResponseTimeoutError` if no valid frame arrives in time.
        """
        with self._t.transaction():
            if not self._reporting:
                raise ReportingError("periodic reporting is disabled; call start_reporting() first")
            self._t.discard_input()
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                for frame in self._t.read_frames(deadline):
                    if not isinstance(frame, ProtocolError):
                        return frame
            raise ResponseTimeoutError(f"no report frame within {timeout}s")
