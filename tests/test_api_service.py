"""Tests for service fingerprint helpers."""

from __future__ import annotations

from unittest.mock import patch

from ofx.api.service import detect_protocol, scan_banner


class _FakeSocket:
    def __init__(self, payload: bytes | OSError, *, close_error: bool = False) -> None:
        self.payload = payload
        self.close_error = close_error
        self.closed = False

    def recv(self, max_bytes: int) -> bytes:
        if isinstance(self.payload, OSError):
            raise self.payload
        return self.payload[:max_bytes]

    def close(self) -> None:
        self.closed = True
        if self.close_error:
            raise OSError("close failed")


def test_detect_protocol_uses_known_ports() -> None:
    assert detect_protocol(22) == "ssh"
    assert detect_protocol(443) == "https"


def test_scan_banner_returns_decoded_banner() -> None:
    sock = _FakeSocket(b"SSH-2.0-OpenSSH_9.7\r\n")

    with patch("socket.create_connection", return_value=sock):
        info = scan_banner("example.com", 22, timeout=0.1)

    assert info.banner == "SSH-2.0-OpenSSH_9.7"
    assert info.protocol == "ssh"
    assert info.tls is False
    assert sock.closed is True


def test_scan_banner_treats_socket_read_failures_as_missing_banner() -> None:
    sock = _FakeSocket(TimeoutError("timed out"), close_error=True)

    with patch("socket.create_connection", return_value=sock):
        info = scan_banner("example.com", 12345, timeout=0.1)

    assert info.banner is None
    assert info.protocol is None
    assert sock.closed is True
