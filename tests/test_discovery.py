"""Test AirTouch 3 discovery helpers."""

import socket
from unittest.mock import AsyncMock, patch

from pyairtouch3.discovery import (
    DISCOVERY_MESSAGE,
    DISCOVERY_PORT,
    AirTouch3Discovery,
    async_discover_targets,
    parse_discovery_payload,
)


class _FakeSocket:
    """Fake socket for discovery tests."""

    def __init__(self, *, bind_error: OSError | None = None) -> None:
        """Initialize the fake socket."""
        self.bind_error = bind_error
        self.closed = False

    def setblocking(self, _flag: bool) -> None:
        """Set blocking mode."""

    def setsockopt(self, _level: int, _optname: int, _value: int) -> None:
        """Set a socket option."""

    def bind(self, _address: tuple[str, int]) -> None:
        """Bind the fake socket."""
        if self.bind_error:
            raise self.bind_error

    def getsockname(self) -> tuple[str, int]:
        """Return a socket name."""
        return ("0.0.0.0", DISCOVERY_PORT)

    def close(self) -> None:
        """Close the fake socket."""
        self.closed = True


class _FakeLoop:
    """Fake event loop socket helpers for discovery tests."""

    def __init__(
        self,
        packets: list[tuple[bytes, tuple[str, int]] | BaseException],
        *,
        send_error_target: str | None = None,
    ) -> None:
        """Initialize the fake loop."""
        self.packets = packets
        self.send_error_target = send_error_target
        self.sent: list[tuple[str, int]] = []

    def time(self) -> float:
        """Return a fake loop time."""
        return 0

    async def sock_sendto(
        self, _sock: _FakeSocket, _data: bytes, addr: tuple[str, int]
    ) -> None:
        """Fake sending to a socket."""
        self.sent.append(addr)
        if addr[0] == self.send_error_target:
            raise OSError("send failed")

    async def sock_recvfrom(
        self, _sock: _FakeSocket, _buffer_size: int
    ) -> tuple[bytes, tuple[str, int]]:
        """Fake receiving from a socket."""
        packet = self.packets.pop(0)
        if isinstance(packet, BaseException):
            raise packet
        return packet


def test_parse_discovery_payload() -> None:
    """Test parsing an AirTouch 3 UDP discovery reply."""
    discovery = parse_discovery_payload(b"10.200.5.20,F0FE6B772324,AirTouch3")

    assert discovery
    assert discovery.host == "10.200.5.20"
    assert discovery.mac == "F0FE6B772324"
    assert discovery.model == "AirTouch3"


def test_parse_discovery_payload_rejects_other_models() -> None:
    """Test discovery ignores non-AirTouch replies."""
    assert parse_discovery_payload(b"10.200.5.20,F0FE6B772324,Other") is None
    assert parse_discovery_payload(b"HF-A11ASSISTHREAD") is None
    assert parse_discovery_payload(b"not-an-ip,F0FE6B772324,AirTouch3") is None
    assert parse_discovery_payload(b"\xff") is None


async def test_async_discover_targets_no_targets() -> None:
    """Test discovery returns no devices when no targets are available."""
    assert await async_discover_targets([], 1) == []


async def test_async_discover_targets_bind_error() -> None:
    """Test discovery handles socket bind errors."""
    fake_socket = _FakeSocket(bind_error=OSError("bind failed"))
    with patch("pyairtouch3.discovery.socket.socket") as socket_mock:
        socket_mock.return_value = fake_socket
        assert await async_discover_targets(["10.200.5.255"], 1) == []

    socket_mock.assert_called_once_with(socket.AF_INET, socket.SOCK_DGRAM)
    assert fake_socket.closed


async def test_async_discover_targets_replies() -> None:
    """Test discovery sends requests and parses replies."""
    fake_socket = _FakeSocket()
    fake_loop = _FakeLoop(
        [
            (DISCOVERY_MESSAGE, ("10.200.5.100", DISCOVERY_PORT)),
            (b"not-airtouch", ("10.200.5.10", DISCOVERY_PORT)),
            (
                b"10.200.5.20,F0FE6B772324,AirTouch3",
                ("10.200.5.20", DISCOVERY_PORT),
            ),
            TimeoutError(),
        ],
        send_error_target="10.200.5.254",
    )

    with (
        patch("pyairtouch3.discovery.socket.socket") as socket_mock,
        patch("pyairtouch3.discovery.asyncio.get_running_loop", return_value=fake_loop),
        patch("pyairtouch3.discovery.asyncio.sleep", AsyncMock()),
    ):
        socket_mock.return_value = fake_socket
        discoveries = await async_discover_targets(["10.200.5.254", "10.200.5.255"], 1)

    assert discoveries == [
        AirTouch3Discovery(host="10.200.5.20", mac="F0FE6B772324", model="AirTouch3")
    ]
    assert fake_loop.sent == [
        ("10.200.5.254", DISCOVERY_PORT),
        ("10.200.5.255", DISCOVERY_PORT),
        ("10.200.5.254", DISCOVERY_PORT),
        ("10.200.5.255", DISCOVERY_PORT),
    ]
    assert fake_socket.closed


async def test_async_discover_targets_receive_error() -> None:
    """Test discovery handles receive errors."""
    fake_socket = _FakeSocket()
    fake_loop = _FakeLoop([OSError("receive failed")])

    with (
        patch("pyairtouch3.discovery.socket.socket") as socket_mock,
        patch("pyairtouch3.discovery.asyncio.get_running_loop", return_value=fake_loop),
        patch("pyairtouch3.discovery.asyncio.sleep", AsyncMock()),
    ):
        socket_mock.return_value = fake_socket
        assert await async_discover_targets(["10.200.5.255"], 1) == []

    assert fake_socket.closed
