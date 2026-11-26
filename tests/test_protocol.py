"""Findings 3, 7, 9: golden encodings, strict frame parsing, stream framing."""

from decimal import Decimal

import pytest
from fake_device import report_frame, status_frame

from dc6006l import DeviceError, ProtocolError, RegulationMode, Report, Status
from dc6006l import protocol as p

# -- encoding ------------------------------------------------------------------


@pytest.mark.parametrize(
    "fn,units,expected",
    [
        (p.encode_voltage, 0, b"V0000\r\n"),
        (p.encode_voltage, 100, b"V0100\r\n"),
        (p.encode_voltage, 6000, b"V6000\r\n"),
        (p.encode_current, 500, b"I0500\r\n"),
        (p.encode_ovp, 500, b"B0500\r\n"),
        (p.encode_ocp, 500, b"D0500\r\n"),
    ],
)
def test_golden_encoding(fn, units, expected):
    assert fn(units) == expected


@pytest.mark.parametrize("fn,units", [(p.encode_voltage, 6001), (p.encode_voltage, -1), (p.encode_ovp, 19)])
def test_encoder_rejects_out_of_range_units(fn, units):
    with pytest.raises(ValueError):
        fn(units)


def test_encoder_rejects_non_int():
    with pytest.raises(TypeError):
        p.encode_voltage(1.0)
    with pytest.raises(TypeError):
        p.encode_voltage(True)


def test_simple_commands():
    assert p.encode_simple("N") == b"N\r\n"
    assert p.encode_simple("F") == b"F\r\n"
    with pytest.raises(ValueError):
        p.encode_simple("X")


# -- parsing -------------------------------------------------------------------

DOC_EXAMPLE = b"0199A0700A0139A0A029A0A0A1A"  # command_list.md "on" example


def test_parse_report_documented_example():
    r = p.parse_report(DOC_EXAMPLE)
    assert r == Report(
        voltage=Decimal("1.99"), current=Decimal("0.700"), power=Decimal("1.39"), unknown_p1=0,
        temperature=29, mode=RegulationMode.CV, error_code=0, output_on=True, raw=DOC_EXAMPLE,
    )
    assert r.error is DeviceError.NONE


def test_parse_status_fields():
    raw = status_frame(v=1234, i=567, p=700, out=1, mode=1, err=2, vset=1500, iset=2000,
                       ovp=1600, ocp=2500, opp=12345, ten=1, hh=1, mm=2, ss=3)
    assert len(raw) == p.STATUS_LEN
    s = p.parse_status(raw)
    assert isinstance(s, Status)
    assert (s.voltage, s.current, s.power) == (Decimal("12.34"), Decimal("0.567"), Decimal("7.00"))
    assert s.mode is RegulationMode.CC and s.output_on and s.error is DeviceError.OVER_CURRENT
    assert (s.voltage_set, s.current_set) == (Decimal("15.00"), Decimal("2.000"))
    assert (s.ovp, s.ocp, s.opp) == (Decimal("16.00"), Decimal("2.500"), Decimal("123.45"))
    assert (s.timer_enabled, s.timer_hours, s.timer_minutes, s.timer_seconds) == (True, 1, 2, 3)


@pytest.mark.parametrize(
    "raw",
    [
        DOC_EXAMPLE[:-1],  # truncated
        DOC_EXAMPLE + b"0",  # extended
        DOC_EXAMPLE.replace(b"A", b"B", 1),  # wrong delimiter
        b"0x99A0700A0139A0A029A0A0A1A",  # non-numeric
        b"0199A0700A0139A0A029A0A1A",  # missing field
        b"",
        "0199A0700A0139A0A029A0A0A1А".encode("utf-8"),  # non-ASCII
    ],
)
def test_malformed_report_rejected(raw):
    with pytest.raises(ProtocolError):
        p.parse_report(raw)


@pytest.mark.parametrize(
    "raw",
    [
        status_frame()[:-1],
        status_frame() + b"0",
        status_frame()[2:],  # missing KB
        b"KX" + status_frame()[2:],
        status_frame().replace(b"6100", b"61x0"),
    ],
)
def test_malformed_status_rejected(raw):
    with pytest.raises(ProtocolError):
        p.parse_status(raw)


@pytest.mark.parametrize(
    "raw",
    [report_frame(mode=2), report_frame(out=2), report_frame(out=9)],
)
def test_unknown_safety_enum_rejected(raw):
    with pytest.raises(ProtocolError):
        p.parse_report(raw)


def test_unknown_error_code_preserved_not_invented():
    r = p.parse_report(report_frame(err=7))
    assert r.error_code == 7 and r.error is None


@pytest.mark.parametrize("kw", [dict(ten=2), dict(mm=60), dict(ss=99)])
def test_invalid_status_extension_rejected(kw):
    with pytest.raises(ProtocolError):
        p.parse_status(status_frame(**kw))


# -- stream framing ------------------------------------------------------------


def test_scanner_fragmented_byte_by_byte():
    sc = p.FrameScanner()
    stream = status_frame(out=1) + report_frame(v=100) + report_frame(v=200)
    out = []
    for b in stream:
        out += sc.feed(bytes([b]))
    assert [type(f) for f in out] == [Status, Report, Report]
    assert [f.voltage for f in out[1:]] == [Decimal("1.00"), Decimal("2.00")]
    assert sc.discarded == 0


def test_scanner_does_not_emit_inner_report_of_partial_status():
    sc = p.FrameScanner()
    frame = status_frame()
    assert sc.feed(frame[:40]) == []  # inner report body is complete, must wait
    out = sc.feed(frame[40:])
    assert len(out) == 1 and isinstance(out[0], Status)


def test_scanner_resyncs_after_garbage_and_mid_frame_start():
    sc = p.FrameScanner()
    stream = b"\x00garbage" + report_frame(v=1)[10:] + report_frame(v=2) + b"KB12" + report_frame(v=3)
    out = sc.feed(stream)
    assert [f.voltage for f in out] == [Decimal("0.02"), Decimal("0.03")]
    assert sc.discarded > 0


def test_scanner_returns_invalid_frames_as_errors():
    sc = p.FrameScanner()
    out = sc.feed(report_frame(out=5) + report_frame(v=7))
    assert isinstance(out[0], ProtocolError) and isinstance(out[1], Report)


def test_scanner_buffer_bounded():
    sc = p.FrameScanner()
    sc.feed(b"x" * 10_000)
    assert sc.pending <= sc.MAX_BUFFER
