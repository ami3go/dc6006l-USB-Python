"""Exception hierarchy for the DC6006L driver.

Every exception raised deliberately by this package derives from
:class:`DC6006LError`, so callers can catch the whole family at once.
"""

from __future__ import annotations

from typing import Any, Optional


class DC6006LError(Exception):
    """Base class for all driver errors."""


class ValidationError(DC6006LError, ValueError):
    """A requested value was rejected before any serial I/O took place."""


class PortNotFoundError(DC6006LError):
    """The requested serial port does not exist on this system."""


class NotConnectedError(DC6006LError):
    """An operation was attempted while the connection is not open."""


class TransportError(DC6006LError):
    """The serial port failed (write/read error, device unplugged, ...).

    The connection is closed when this is raised; call ``open()`` again
    to reconnect.
    """


class ReportingError(DC6006LError):
    """``read_report()`` was called while periodic reporting is disabled."""


class ResponseTimeoutError(DC6006LError):
    """No valid frame was received before the deadline."""


class ProtocolError(DC6006LError):
    """A received frame matched the frame grammar but carries invalid content."""

    def __init__(self, message: str, raw: Optional[bytes] = None) -> None:
        super().__init__(message)
        self.raw = raw


class VerificationError(DC6006LError):
    """The device read back a value different from the one requested.

    The command *was* delivered and the device is now in the state reported
    by ``status``; the caller must decide how to proceed. ``output_disabled``
    tells whether the driver switched the output off as a fail-safe reaction.
    """

    def __init__(
        self,
        message: str,
        *,
        parameter: str,
        requested: Any,
        actual: Any,
        status: Any,
        output_disabled: bool = False,
    ) -> None:
        super().__init__(message)
        self.parameter = parameter
        self.requested = requested
        self.actual = actual
        self.status = status
        self.output_disabled = output_disabled


class IndeterminateError(DC6006LError):
    """A command was written but its effect could not be confirmed.

    The device may or may not have applied the command. The driver does not
    resend setpoint/protection commands automatically in this situation.
    """

    def __init__(self, message: str, *, command: str) -> None:
        super().__init__(message)
        self.command = command


class OutputStateError(DC6006LError):
    """Output ON/OFF could not be confirmed after the bounded retry policy.

    ``last_status`` is the last valid status read (``None`` if none was
    received). When it is ``None`` the output state is UNKNOWN; never assume
    either ON or OFF.
    """

    def __init__(self, message: str, *, requested_on: bool, last_status: Any) -> None:
        super().__init__(message)
        self.requested_on = requested_on
        self.last_status = last_status
