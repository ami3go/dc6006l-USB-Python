"""Serial transport: connection lifecycle, locking, paced writes, framed reads."""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator, List, Optional, Union

from .exceptions import NotConnectedError, PortNotFoundError, ProtocolError, TransportError
from .protocol import Frame, FrameScanner

log = logging.getLogger(__name__)

BAUDRATE = 115200

SerialFactory = Callable[..., Any]


def list_ports() -> List[str]:
    """Return the device names of all serial ports present on this system."""
    import serial.tools.list_ports

    return [p.device for p in serial.tools.list_ports.comports()]


def _default_factory(port: str, **kwargs: Any) -> Any:
    import serial

    return serial.Serial(port=port, **kwargs)


class SerialTransport:
    """Owns the serial port and the byte stream coming from the device.

    * One re-entrant lock serialises whole transactions (:meth:`transaction`).
      One physical connection supports one in-flight transaction.
    * Writes are paced by ``min_command_interval`` seconds. The original
      driver always slept ~0.1 s before writing and the README reports
      corrupted setpoints; pacing is kept as a precaution.
    * Reads go through a :class:`FrameScanner`; there are no fixed-size reads
      and no blanket buffer resets. Stale input is drained explicitly via
      :meth:`discard_input`, and the number of dropped bytes is logged.
    """

    def __init__(
        self,
        port: str,
        *,
        serial_factory: Optional[SerialFactory] = None,
        check_port_exists: bool = True,
        read_timeout: float = 0.02,
        write_timeout: float = 1.0,
        min_command_interval: float = 0.1,
    ) -> None:
        self.port = port
        self._factory = serial_factory or _default_factory
        self._check_port = check_port_exists and serial_factory is None
        self._read_timeout = read_timeout
        self._write_timeout = write_timeout
        self._interval = min_command_interval
        self._ser: Any = None
        self._lock = threading.RLock()
        self._scanner = FrameScanner()
        self._last_write = float("-inf")

    # -- lifecycle --------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return self._ser is not None

    def open(self) -> None:
        """Open the port. Calling it while already open is a no-op."""
        with self._lock:
            if self._ser is not None:
                return
            if self._check_port:
                ports = list_ports()
                if self.port not in ports:
                    raise PortNotFoundError(
                        f"serial port {self.port!r} not found; available ports: {ports}"
                    )
            try:
                self._ser = self._factory(
                    self.port,
                    baudrate=BAUDRATE,
                    timeout=self._read_timeout,
                    write_timeout=self._write_timeout,
                )
            except Exception as exc:
                raise TransportError(f"cannot open {self.port!r}: {exc}") from exc
            self._scanner = FrameScanner()
            self._last_write = float("-inf")
            log.debug("opened %s", self.port)

    def close(self) -> None:
        """Close the port. Safe to call at any time, any number of times."""
        with self._lock:
            ser, self._ser = self._ser, None
            if ser is None:
                return
            try:
                ser.close()
            except Exception as exc:  # pragma: no cover - best effort
                log.warning("error while closing %s: %s", self.port, exc)
            log.debug("closed %s", self.port)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Hold the transport lock for a complete command/response exchange."""
        with self._lock:
            self._require_open()
            yield

    def _require_open(self) -> None:
        if self._ser is None:
            raise NotConnectedError("connection is not open; call open() first")

    def _fail(self, what: str, exc: BaseException) -> TransportError:
        self.close()
        return TransportError(f"{what} failed on {self.port!r}: {exc}; connection closed")

    # -- I/O ----------------------------------------------------------------

    def write(self, data: bytes, *, discard_input_first: bool = False) -> None:
        """Write one encoded command, respecting the minimum command interval.

        With ``discard_input_first`` all input received so far is dropped
        right before the write (after pacing), so that subsequent reads only
        see data the device produced after this command.

        Success only means the bytes were handed to the OS; it says nothing
        about whether the device accepted the command.
        """
        with self._lock:
            self._require_open()
            wait = self._last_write + self._interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            if discard_input_first:
                self.discard_input()
            try:
                n = self._ser.write(data)
                self._ser.flush()
            except Exception as exc:
                raise self._fail("write", exc) from exc
            finally:
                self._last_write = time.monotonic()
            if n is not None and n != len(data):
                raise self._fail("write", RuntimeError(f"short write {n}/{len(data)} bytes"))
            log.debug("tx %r", data)

    def _read_chunk(self) -> bytes:
        try:
            waiting = self._ser.in_waiting
            data = self._ser.read(waiting if waiting else 1)
        except Exception as exc:
            raise self._fail("read", exc) from exc
        return bytes(data or b"")

    def discard_input(self) -> int:
        """Drop all bytes already received (and any partial frame).

        Used before a command so that only data produced after it is
        considered. Returns the number of bytes dropped.
        """
        with self._lock:
            self._require_open()
            dropped = self._scanner.pending
            self._scanner.reset()
            while True:
                try:
                    waiting = self._ser.in_waiting
                except Exception as exc:
                    raise self._fail("read", exc) from exc
                if not waiting:
                    break
                try:
                    data = self._ser.read(waiting)
                except Exception as exc:
                    raise self._fail("read", exc) from exc
                if not data:
                    break
                dropped += len(data)
            if dropped:
                log.debug("discarded %d stale input bytes", dropped)
            return dropped

    def read_frames(self, deadline: float) -> List[Union[Frame, ProtocolError]]:
        """Read until at least one frame is available or ``deadline`` passes.

        ``deadline`` is a :func:`time.monotonic` timestamp. Returns all frames
        decoded so far (possibly an empty list on timeout).
        """
        with self._lock:
            self._require_open()
            while True:
                data = self._read_chunk()
                frames = self._scanner.feed(data) if data else []
                if frames:
                    for f in frames:
                        if isinstance(f, ProtocolError):
                            log.warning("invalid frame %r: %s", f.raw, f)
                    return frames
                if time.monotonic() >= deadline:
                    return []
