"""Finding 2 (no clamping, strict validation) and finding 3/1 (encoding)."""

import math
from decimal import Decimal
from fractions import Fraction

import pytest

from dc6006l import ValidationError
from dc6006l import protocol as p
from dc6006l import validation as v


@pytest.mark.parametrize(
    "q,value,units",
    [
        (v.VOLTAGE, 0, 0),
        (v.VOLTAGE, 60, 6000),
        (v.VOLTAGE, 0.01, 1),
        (v.VOLTAGE, Decimal("12.34"), 1234),
        (v.VOLTAGE, 0.1 + 0.2, 30),  # float noise accepted
        (v.CURRENT, 6, 6000),
        (v.CURRENT, 1.001, 1001),
        (v.OVP, 0.2, 20),
        (v.OVP, 61, 6100),
        (v.OCP, 0, 0),
        (v.CURRENT, Fraction(1, 2), 500),
    ],
)
def test_valid_values(q, value, units):
    assert v.to_units(value, q) == units


@pytest.mark.parametrize(
    "q,value",
    [
        (v.VOLTAGE, 60.01),
        (v.VOLTAGE, 100),
        (v.VOLTAGE, -0.01),
        (v.CURRENT, 6.001),
        (v.CURRENT, -5),
        (v.OVP, 0.19),
        (v.OVP, 61.01),
        (v.OCP, 6.001),
    ],
)
def test_out_of_range_rejected_not_clamped(q, value):
    with pytest.raises(ValidationError, match="outside the supported range"):
        v.to_units(value, q)


@pytest.mark.parametrize(
    "value", [True, False, "5", None, [5], math.nan, math.inf, -math.inf, Decimal("NaN"), Decimal("Infinity")]
)
def test_non_numeric_rejected(value):
    with pytest.raises(ValidationError):
        v.to_units(value, v.VOLTAGE)


@pytest.mark.parametrize("q,value", [(v.VOLTAGE, 1.005), (v.CURRENT, 1.0004), (v.OVP, 0.295)])
def test_off_resolution_rejected_not_rounded(q, value):
    with pytest.raises(ValidationError, match="resolution"):
        v.to_units(value, q)


def test_validation_error_is_value_error():
    assert issubclass(ValidationError, ValueError)


def test_every_current_step_encodes_exactly():
    # Old set_i_out sent 48 of these 1 mA low (e.g. 1.001 -> I1000).
    for c in range(0, 6001):
        assert p.encode_current(v.to_units(c / 1000, v.CURRENT)) == f"I{c:04d}\r\n".encode()


def test_every_voltage_step_encodes_exactly():
    for c in range(0, 6001):
        assert p.encode_voltage(v.to_units(c / 100, v.VOLTAGE)) == f"V{c:04d}\r\n".encode()


def test_every_protection_step_encodes_exactly():
    # Old set_volt_protect sent 287 values 10 mV low (e.g. 0.29 -> B0028).
    for c in range(20, 6101):
        assert p.encode_ovp(v.to_units(c / 100, v.OVP)) == f"B{c:04d}\r\n".encode()
    for c in range(0, 6001):
        assert p.encode_ocp(v.to_units(c / 1000, v.OCP)) == f"D{c:04d}\r\n".encode()
