"""Driver behaviour against the fake device (findings 1-12)."""

import threading
from decimal import Decimal

import pytest
from fake_device import report_frame, status_frame

from dc6006l import (
    DC6006L,
    IndeterminateError,
    NotConnectedError,
    OutputStateError,
    PortNotFoundError,
    ProtocolError,
    ReportingError,
    ResponseTimeoutError,
    Status,
    TransportError,
    ValidationError,
    VerificationError,
)


def cmds(dev):
    return [c for _, c in dev.commands]


# -- lifecycle (finding 10) -----------------------------------------------------


def test_close_before_open_and_twice(make_psu):
    psu = make_psu()
    psu.close()
    psu.close()
    assert not psu.is_open


def test_open_is_idempotent_and_stops_reporting(make_psu, dev):
    dev.reporting = True
    psu = make_psu()
    psu.open()
    psu.open()
    assert dev.open_count == 1
    assert cmds(dev) == ["W"] and not dev.reporting and not psu.reporting


def test_reopen_after_close(make_psu, dev):
    psu = make_psu().open()
    psu.close()
    psu.open()
    assert dev.open_count == 2
    assert isinstance(psu.get_status(), Status)


@pytest.mark.parametrize(
    "call",
    [
        lambda d: d.get_status(),
        lambda d: d.set_voltage(5),
        lambda d: d.output_on(),
        lambda d: d.output_off(),
        lambda d: d.start_reporting(),
        lambda d: d.read_report(),
    ],
)
def test_operations_after_close_raise(make_psu, call):
    psu = make_psu().open()
    psu.close()
    with pytest.raises(NotConnectedError):
        call(psu)


def test_context_manager_closes(make_psu):
    with make_psu() as psu:
        assert psu.is_open
    assert not psu.is_open


def test_port_not_found(monkeypatch):
    import dc6006l.transport as t

    monkeypatch.setattr(t, "list_ports", lambda: ["COM1"])
    with pytest.raises(PortNotFoundError, match="COM9"):
        DC6006L("COM9").open()


def test_factory_exception_becomes_transport_error():
    def boom(port, **kw):
        raise OSError("busy")

    with pytest.raises(TransportError):
        DC6006L("X", serial_factory=boom).open()


def test_write_failure_closes_connection(psu, dev):
    dev.fail_write = True
    with pytest.raises(TransportError):
        psu.output_off()
    assert not psu.is_open


def test_short_write_is_transport_error(psu, dev):
    dev.short_write = True
    with pytest.raises(TransportError):
        psu.get_status()
    assert not psu.is_open


def test_read_failure_closes_connection(psu, dev):
    dev.fail_read = True
    with pytest.raises(TransportError):
        psu.get_status()
    assert not psu.is_open


# -- status (findings 9, 11) ----------------------------------------------------


def test_get_status_and_reporting_restored(psu, dev):
    dev.vset, dev.ovp = 1234, 1500
    s = psu.get_status()
    assert s.voltage_set == Decimal("12.34") and s.ovp == Decimal("15.00")
    assert not dev.reporting, "get_status must not leave reporting enabled"
    assert cmds(dev)[-3:] == ["W", "Q", "W"]


def test_get_status_keeps_reporting_when_enabled(psu, dev):
    psu.start_reporting()
    psu.get_status()
    assert dev.reporting and psu.reporting


def test_get_status_fragmented(psu, dev):
    dev.chunk = 1
    assert isinstance(psu.get_status(), Status)


def test_get_status_timeout(psu, dev):
    dev.answer_status = False
    with pytest.raises(ResponseTimeoutError):
        psu.get_status()
    assert cmds(dev).count("Q") == 2  # bounded: status_attempts


def test_get_status_only_malformed(psu, dev):
    dev.status_mangler = lambda f: f.replace(b"A0A0A", b"A9A0A", 1)  # invalid CV/CC
    with pytest.raises(ProtocolError):
        psu.get_status()


def test_get_status_ignores_truncated_frame(psu, dev):
    dev.status_mangler = lambda f: f[:50]
    with pytest.raises(ResponseTimeoutError):
        psu.get_status()


def test_get_status_ignores_stale_buffered_status(psu, dev):
    dev.tx += status_frame(vset=9999)
    dev.answer_status = False
    with pytest.raises(ResponseTimeoutError):
        psu.get_status()


# -- setpoints (findings 2, 3, 12) ----------------------------------------------


@pytest.mark.parametrize(
    "method,value,attr,units",
    [
        ("set_voltage", 12.34, "vset", 1234),
        ("set_current", 1.001, "iset", 1001),
        ("set_ovp", 0.29, "ovp", 29),
        ("set_ocp", 1.001, "ocp", 1001),
    ],
)
def test_setter_success_verified(psu, dev, method, value, attr, units):
    s = getattr(psu, method)(value)
    assert getattr(dev, attr) == units
    assert isinstance(s, Status)


@pytest.mark.parametrize("method", ["set_voltage", "set_current", "set_ovp", "set_ocp"])
@pytest.mark.parametrize("value", [100, -1, True, "5", float("nan"), float("inf"), 1.0004])
def test_invalid_input_writes_nothing(psu, dev, method, value):
    before = list(dev.commands)
    with pytest.raises(ValidationError):
        getattr(psu, method)(value)
    assert dev.commands == before


def test_voltage_mismatch_raises_and_disables_output(psu, dev):
    dev.output = True
    dev.setpoint_transform = lambda letter, u: u * 10 if letter == "V" else u  # 0.7 V -> 7 V
    with pytest.raises(VerificationError) as ei:
        psu.set_voltage(0.7)
    e = ei.value
    assert e.requested == Decimal("0.70") and e.actual == Decimal("7.00")
    assert e.output_disabled and not dev.output
    assert cmds(dev).count("V0070") == 1


def test_mismatch_output_off_not_touched(psu, dev):
    dev.setpoint_transform = lambda letter, u: u + 1
    with pytest.raises(VerificationError) as ei:
        psu.set_current(1)
    assert not ei.value.output_disabled
    assert "F" not in cmds(dev)


def test_mismatch_failsafe_can_be_disabled(make_psu, dev):
    psu = make_psu(disable_output_on_mismatch=False).open()
    dev.output = True
    dev.setpoint_transform = lambda letter, u: u + 1
    with pytest.raises(VerificationError):
        psu.set_voltage(5)
    assert dev.output


def test_setter_dropped_command_is_mismatch_not_success(psu, dev):
    dev.drop.add("V")
    with pytest.raises(VerificationError):
        psu.set_voltage(12)


def test_setter_no_readback_is_indeterminate_and_not_resent(psu, dev):
    dev.answer_status = False
    with pytest.raises(IndeterminateError) as ei:
        psu.set_voltage(5)
    assert ei.value.command == "V"
    assert cmds(dev).count("V0500") == 1


# -- protection (finding 1) -----------------------------------------------------


def test_ovp_mismatch(psu, dev):
    dev.drop.add("B")
    with pytest.raises(VerificationError) as ei:
        psu.set_ovp(5)
    assert ei.value.parameter == "ovp" and ei.value.actual == Decimal("61.00")


def test_ocp_malformed_readback(psu, dev):
    dev.status_mangler = lambda f: f.replace(b"KB", b"KC")
    with pytest.raises(IndeterminateError):
        psu.set_ocp(1)


def test_ocp_verified_against_current_not_voltage(psu, dev):
    dev.setpoint_transform = lambda letter, u: 1234 if letter == "D" else u
    with pytest.raises(VerificationError) as ei:
        psu.set_ocp(1)
    assert ei.value.actual == Decimal("1.234")


# -- output control (findings 4, 5) ---------------------------------------------


def test_output_on_off(psu, dev):
    assert psu.output_on().output_on and dev.output
    assert not psu.output_off().output_on and not dev.output


def test_output_on_works_with_reporting_disabled(psu, dev):
    assert not psu.reporting
    assert psu.output_on().output_on


def test_output_off_stale_off_frames_not_trusted(psu, dev):
    """Old driver returned True here: stale OFF frames, F lost, output ON."""
    dev.output = True
    dev.reporting = True
    dev.tx += report_frame(out=0) * 5 + status_frame(out=0)
    dev.drop.add("F")
    with pytest.raises(OutputStateError) as ei:
        psu.output_off()
    assert ei.value.last_status.output_on is True
    assert dev.output


def test_output_off_retry_then_success(psu, dev):
    dev.output = True
    dev.drop_once.append("F")
    s = psu.output_off()
    assert not s.output_on and cmds(dev).count("F") == 2


def test_output_retry_exhaustion_unknown_state(psu, dev):
    dev.answer_status = False
    with pytest.raises(OutputStateError, match="UNKNOWN") as ei:
        psu.output_on()
    assert ei.value.last_status is None
    assert cmds(dev).count("N") == 3


def test_output_on_refused_by_device_error(psu, dev):
    dev.error = 1
    with pytest.raises(OutputStateError) as ei:
        psu.output_on()
    assert ei.value.last_status.error_code == 1


# -- reporting (finding 11) -----------------------------------------------------


def test_read_report_requires_reporting(psu):
    with pytest.raises(ReportingError):
        psu.read_report()


def test_read_report_is_fresh(psu, dev):
    psu.start_reporting()
    dev.output = True
    dev.vset = 500
    dev.tx += report_frame(v=4321)  # stale
    r = psu.read_report(timeout=0.2)
    assert r.voltage == Decimal("5.00")


def test_stop_reporting(psu, dev):
    psu.start_reporting()
    psu.stop_reporting()
    assert not dev.reporting and not psu.reporting


# -- concurrency (finding 6) ----------------------------------------------------


def test_concurrent_callers_do_not_interleave(psu, dev):
    errors = []

    def worker(i):
        try:
            for k in range(5):
                psu.set_voltage((i * 10 + k) / 10)
                psu.get_status()
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(1, 5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    # Each setter transaction = V, W, Q, W from a single thread, contiguous.
    log = dev.commands
    for idx, (tid, c) in enumerate(log):
        if c.startswith("V"):
            assert [x[1] for x in log[idx : idx + 4]] == [c, "W", "Q", "W"]
            assert {x[0] for x in log[idx : idx + 4]} == {tid}
