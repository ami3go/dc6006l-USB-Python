"""Software model of the DC6006L serial behaviour, with fault injection.

Behaviour modelled (from the original driver and command_list.md):
* commands are ASCII + CR LF;
* ``Q`` enables reporting and makes the device send one 66-byte ``KB`` status
  frame, followed by 27-byte report frames while reporting is on;
* ``W`` disables reporting; ``N``/``F`` switch the output; ``V``/``I``/``B``/``D``
  set setpoints/limits in protocol units.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, List, Optional, Set, Tuple


def report_frame(v=0, i=0, p=0, p1=0, temp=29, mode=0, err=0, out=0) -> bytes:
    return f"{v:04d}A{i:04d}A{p:04d}A{p1}A{temp:03d}A{mode}A{err}A{out}A".encode()


def status_frame(
    v=0, i=0, p=0, p1=0, temp=29, mode=0, err=0, out=0,
    vset=500, iset=1000, ovp=6100, ocp=6000, opp=36000, ten=0, hh=0, mm=0, ss=0,
) -> bytes:
    return (
        b"KB"
        + report_frame(v, i, p, p1, temp, mode, err, out)
        + f"{vset:04d}A{iset:04d}A{ovp:04d}A{ocp:04d}A{opp:05d}A{ten}A{hh:02d}A{mm:02d}A{ss:02d}A".encode()
    )


class FakeDevice:
    def __init__(self) -> None:
        self.vset, self.iset, self.ovp, self.ocp = 500, 1000, 6100, 6000
        self.output = False
        self.reporting = False
        self.error = 0
        self.tx = bytearray()  # device -> host
        self._rx = bytearray()  # host -> device (partial command)
        self.commands: List[Tuple[int, str]] = []  # (thread id, command)
        self.lock = threading.Lock()
        self.open_count = 0
        # --- fault injection ---
        self.drop: Set[str] = set()  # command letters ignored by the device
        self.drop_once: List[str] = []  # command letters ignored once, in order
        self.answer_status = True  # send KB frame on Q
        self.status_mangler: Optional[Callable[[bytes], bytes]] = None
        self.setpoint_transform: Optional[Callable[[str, int], int]] = None
        self.chunk: Optional[int] = None  # max bytes returned per read()
        self.fail_write = False
        self.fail_read = False
        self.short_write = False

    # -- frames -------------------------------------------------------------

    def _measured(self):
        if not self.output:
            return dict(v=0, i=0, p=0, out=0, err=self.error)
        return dict(v=self.vset, i=0, p=0, out=1, err=self.error)

    def make_report(self) -> bytes:
        return report_frame(**self._measured())

    def make_status(self) -> bytes:
        return status_frame(**self._measured(), vset=self.vset, iset=self.iset, ovp=self.ovp, ocp=self.ocp)

    # -- command handling ---------------------------------------------------

    def receive(self, data: bytes) -> None:
        self._rx += data
        while b"\r\n" in self._rx:
            line, _, rest = bytes(self._rx).partition(b"\r\n")
            self._rx = bytearray(rest)
            self._execute(line.decode("ascii"))

    def _execute(self, cmd: str) -> None:
        self.commands.append((threading.get_ident(), cmd))
        letter = cmd[:1]
        if letter in self.drop:
            return
        if self.drop_once and self.drop_once[0] == letter:
            self.drop_once.pop(0)
            return
        if letter in "VIBD":
            units = int(cmd[1:])
            if self.setpoint_transform:
                units = self.setpoint_transform(letter, units)
            attr = {"V": "vset", "I": "iset", "B": "ovp", "D": "ocp"}[letter]
            setattr(self, attr, units)
        elif cmd == "N":
            self.output = self.error == 0
        elif cmd == "F":
            self.output = False
        elif cmd == "Q":
            self.reporting = True
            if self.answer_status:
                frame = self.make_status()
                if self.status_mangler:
                    frame = self.status_mangler(frame)
                self.tx += frame
        elif cmd == "W":
            self.reporting = False

    def serial_factory(self, port, **kwargs):
        self.open_count += 1
        return FakeSerial(self)


class FakeSerial:
    def __init__(self, dev: FakeDevice) -> None:
        self.dev = dev
        self.is_open = True

    @property
    def in_waiting(self) -> int:
        if self.dev.fail_read:
            raise OSError("device disconnected")
        return len(self.dev.tx)

    def write(self, data: bytes) -> int:
        if self.dev.fail_write:
            raise OSError("write failed")
        with self.dev.lock:
            self.dev.receive(bytes(data))
        return len(data) - 1 if self.dev.short_write else len(data)

    def flush(self) -> None:
        pass

    def read(self, n: int = 1) -> bytes:
        if self.dev.fail_read:
            raise OSError("device disconnected")
        with self.dev.lock:
            if not self.dev.tx and self.dev.reporting:
                self.dev.tx += self.dev.make_report()
            if not self.dev.tx:
                out = b""
            else:
                take = min(n, self.dev.chunk or n)
                out = bytes(self.dev.tx[:take])
                del self.dev.tx[:take]
        if not out:
            time.sleep(0.001)
        return out

    def close(self) -> None:
        self.is_open = False
