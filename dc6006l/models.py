"""Immutable data models for decoded device frames."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


class RegulationMode(enum.IntEnum):
    """CV/CC field of the status frame (``command_list.md``)."""

    CV = 0
    CC = 1


class DeviceError(enum.IntEnum):
    """Known values of the error field (``command_list.md``).

    The firmware may report other values; they are kept as the raw
    ``error_code`` and :attr:`Report.error` is ``None`` for them.
    """

    NONE = 0
    OVER_VOLTAGE = 1
    OVER_CURRENT = 2
    OVER_TIME = 3


@dataclass(frozen=True)
class Report:
    """Periodic 27-byte report frame (sent while reporting is enabled).

    Values are measured outputs, not setpoints.
    """

    voltage: Decimal  # V, 0.01 V resolution
    current: Decimal  # A, 0.001 A resolution
    power: Decimal  # W, 0.01 W resolution
    unknown_p1: int  # meaning not established
    temperature: int  # degrees C (assumed)
    mode: RegulationMode
    error_code: int
    output_on: bool
    raw: bytes

    @property
    def error(self) -> Optional[DeviceError]:
        """Known :class:`DeviceError`, or ``None`` if the code is undocumented."""
        try:
            return DeviceError(self.error_code)
        except ValueError:
            return None


@dataclass(frozen=True)
class Status(Report):
    """Full 66-byte status frame (sent in response to ``Q``).

    Field meanings beyond :class:`Report` come from the original driver's
    reverse engineering; see docs/PROTOCOL.md for their evidence level.
    """

    voltage_set: Decimal = Decimal(0)  # V
    current_set: Decimal = Decimal(0)  # A
    ovp: Decimal = Decimal(0)  # V, over-voltage protection limit
    ocp: Decimal = Decimal(0)  # A, over-current protection limit
    opp: Decimal = Decimal(0)  # W, over-power protection limit
    timer_enabled: bool = False
    timer_hours: int = 0
    timer_minutes: int = 0
    timer_seconds: int = 0
