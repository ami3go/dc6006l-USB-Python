"""Python driver for the FNIRSI DC6006L programmable power supply (USB serial).

The serial protocol is reverse-engineered; see docs/PROTOCOL.md.
"""

from .driver import DC6006L
from .exceptions import (
    DC6006LError,
    IndeterminateError,
    NotConnectedError,
    OutputStateError,
    PortNotFoundError,
    ProtocolError,
    ReportingError,
    ResponseTimeoutError,
    TransportError,
    ValidationError,
    VerificationError,
)
from .models import DeviceError, RegulationMode, Report, Status
from .transport import list_ports

__version__ = "1.0.0"

__all__ = [
    "DC6006L",
    "DC6006LError",
    "DeviceError",
    "IndeterminateError",
    "NotConnectedError",
    "OutputStateError",
    "PortNotFoundError",
    "ProtocolError",
    "RegulationMode",
    "Report",
    "ReportingError",
    "ResponseTimeoutError",
    "Status",
    "TransportError",
    "ValidationError",
    "VerificationError",
    "list_ports",
]
