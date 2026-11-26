"""Strict numeric validation and conversion to integer protocol units.

Nothing here performs I/O. Every public setter of the driver calls
:func:`to_units` before touching the serial port, so invalid input can never
produce a serial write.
"""

from __future__ import annotations

import math
import numbers
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Union

from .exceptions import ValidationError

Number = Union[int, float, Decimal]

# Values closer than this to a resolution step are accepted as float noise
# (e.g. 0.1 + 0.2). Anything further away is rejected, not rounded.
_FLOAT_NOISE = Decimal("1e-9")


@dataclass(frozen=True)
class Quantity:
    """Range and resolution of one settable quantity.

    ``resolution`` is the size of one protocol unit; ``min_units``/``max_units``
    are inclusive limits expressed in protocol units.
    """

    name: str
    unit: str
    resolution: Decimal
    min_units: int
    max_units: int
    digits: int = 4

    @property
    def minimum(self) -> Decimal:
        return self.min_units * self.resolution

    @property
    def maximum(self) -> Decimal:
        return self.max_units * self.resolution


# Limits come from the original driver (range_check / set_volt_protect) and
# the nominal 60 V / 6 A rating. They are NOT confirmed for every hardware or
# firmware revision; see docs/PROTOCOL.md.
VOLTAGE = Quantity("voltage", "V", Decimal("0.01"), 0, 6000)
CURRENT = Quantity("current", "A", Decimal("0.001"), 0, 6000)
OVP = Quantity("over-voltage protection", "V", Decimal("0.01"), 20, 6100)
OCP = Quantity("over-current protection", "A", Decimal("0.001"), 0, 6000)


def to_decimal(value: object, name: str) -> Decimal:
    """Convert ``value`` to a finite :class:`Decimal` or raise ValidationError.

    Accepts ``int``, ``float``, :class:`Decimal` and other real numbers.
    Rejects ``bool`` (``True`` would otherwise mean 1 V), strings, NaN and
    infinities.
    """
    if isinstance(value, bool) or not isinstance(value, (numbers.Real, Decimal)):
        raise ValidationError(
            f"{name} must be a real number (int, float or Decimal), got {type(value).__name__}: {value!r}"
        )
    if isinstance(value, Decimal):
        dec = value
    elif isinstance(value, numbers.Integral):
        dec = Decimal(int(value))
    else:
        f = float(value)
        if not math.isfinite(f):
            raise ValidationError(f"{name} must be finite, got {value!r}")
        # str() gives the shortest repr, so 1.001 -> Decimal('1.001'), not the
        # binary expansion 1.000999999...
        dec = Decimal(repr(f))
    if not dec.is_finite():
        raise ValidationError(f"{name} must be finite, got {value!r}")
    return dec


def to_units(value: object, quantity: Quantity) -> int:
    """Validate ``value`` and return it in integer protocol units.

    Raises :class:`ValidationError` if the value is not a finite real number,
    is not a multiple of the resolution (beyond float noise), or lies outside
    the inclusive range. Values are never clamped.
    """
    dec = to_decimal(value, quantity.name)
    try:
        exact = dec / quantity.resolution
        units = exact.quantize(Decimal(1), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:  # pragma: no cover - absurdly large values
        raise ValidationError(f"{quantity.name} {value!r} cannot be represented") from exc
    if abs(exact - units) * quantity.resolution > _FLOAT_NOISE:
        raise ValidationError(
            f"{quantity.name} {value!r} {quantity.unit} is not a multiple of the "
            f"device resolution {quantity.resolution} {quantity.unit}"
        )
    n = int(units)
    if not quantity.min_units <= n <= quantity.max_units:
        raise ValidationError(
            f"{quantity.name} {value!r} {quantity.unit} is outside the supported range "
            f"{quantity.minimum}..{quantity.maximum} {quantity.unit}"
        )
    return n


def from_units(units: int, quantity: Quantity) -> Decimal:
    """Convert integer protocol units back to a Decimal in physical units."""
    return units * quantity.resolution
