"""Test the AirTouch 3 TCP client."""

import asyncio
from unittest.mock import AsyncMock, patch

from pyairtouch3.airtouch_aircon import Aircon
from pyairtouch3.airtouch_message import AirTouchMessage
from pyairtouch3.client import AirTouchClient, AirTouchError
import pytest


class FakeStreamReader:
    """Fake stream reader for AirTouch socket tests."""

    def __init__(self, data: bytes) -> None:
        """Initialize the fake reader."""
        self._data = data

    async def read(self, _limit: int) -> bytes:
        """Return the configured data."""
        return self._data


class FakeStreamWriter:
    """Fake stream writer for AirTouch socket tests."""

    def __init__(self) -> None:
        """Initialize the fake writer."""
        self.written_data: bytes | bytearray | None = None
        self.closed = False
        self.drain = AsyncMock()
        self.wait_closed = AsyncMock()

    def write(self, data: bytes | bytearray) -> None:
        """Store written data."""
        self.written_data = data

    def close(self) -> None:
        """Mark the writer closed."""
        self.closed = True


async def test_fetch_aircon_success() -> None:
    """Test fetching AirTouch data writes the init message and parses the response."""
    aircon = Aircon(1)
    reader = FakeStreamReader(b"\x00" * 520)
    writer = FakeStreamWriter()

    with (
        patch(
            "pyairtouch3.client.asyncio.open_connection",
            AsyncMock(return_value=(reader, writer)),
        ) as open_connection,
        patch("pyairtouch3.client.MessageResponseParser") as parser,
    ):
        parser.return_value.parse.return_value = aircon
        result = await AirTouchClient("1.1.1.1").fetch_aircon()

    assert result is aircon
    open_connection.assert_awaited_once_with("1.1.1.1", 8899)
    assert writer.written_data == bytearray([85, 1, 12, 0, 0, 0, 0, 0, 0, 0, 0, 0, 98])
    writer.drain.assert_awaited_once()
    assert writer.closed is True
    writer.wait_closed.assert_awaited_once()


async def test_fetch_aircon_short_response_raises() -> None:
    """Test short AirTouch responses raise AirTouchError."""
    reader = FakeStreamReader(b"\x00")
    writer = FakeStreamWriter()

    with (
        patch(
            "pyairtouch3.client.asyncio.open_connection",
            AsyncMock(return_value=(reader, writer)),
        ),
        pytest.raises(AirTouchError),
    ):
        await AirTouchClient("1.1.1.1").fetch_aircon()

    assert writer.closed is True


@pytest.mark.parametrize(
    ("method_name", "args", "expected_message"),
    [
        ("toggle_zone", (3,), AirTouchMessage().toggle_zone(3)),
        ("adjust_zone_temperature", (2, 1), AirTouchMessage().set_fan(2, 1)),
        ("toggle_ac_power", (1,), AirTouchMessage().toggle_ac_on_off(1)),
        ("set_mode", (0, 11, 1), AirTouchMessage().set_mode(0, 11, 1)),
        ("set_fan_speed", (0, 2, 4), AirTouchMessage().set_fan_speed(0, 2, 4)),
    ],
)
async def test_semantic_commands_send_protocol_messages(
    method_name: str, args: tuple[int, ...], expected_message: bytearray
) -> None:
    """Test semantic client commands send protocol message bytes."""
    client = AirTouchClient("1.1.1.1")
    send_message = AsyncMock()
    client.send_message = send_message

    await getattr(client, method_name)(*args)

    send_message.assert_awaited_once_with(expected_message)


async def test_fetch_aircon_parse_error_raises() -> None:
    """Test parse errors are surfaced as AirTouchError."""
    reader = FakeStreamReader(b"\x00" * 520)
    writer = FakeStreamWriter()

    with (
        patch(
            "pyairtouch3.client.asyncio.open_connection",
            AsyncMock(return_value=(reader, writer)),
        ),
        patch("pyairtouch3.client.MessageResponseParser") as parser,
    ):
        parser.return_value.parse.side_effect = ValueError("bad response")
        with pytest.raises(AirTouchError):
            await AirTouchClient("1.1.1.1").fetch_aircon()

    assert writer.closed is True


async def test_send_message_writes_and_closes_socket() -> None:
    """Test sending a command writes and closes the socket."""
    reader = FakeStreamReader(b"")
    writer = FakeStreamWriter()

    with patch(
        "pyairtouch3.client.asyncio.open_connection",
        AsyncMock(return_value=(reader, writer)),
    ):
        await AirTouchClient("1.1.1.1").send_message(bytearray(b"command"))

    assert writer.written_data == bytearray(b"command")
    writer.drain.assert_awaited_once()
    assert writer.closed is True
    writer.wait_closed.assert_awaited_once()


async def test_send_message_waits_between_commands() -> None:
    """Test sending commands is paced to avoid overloading the controller."""
    reader = FakeStreamReader(b"")
    writer = FakeStreamWriter()
    client = AirTouchClient("1.1.1.1", command_interval=5)
    client._last_command_at = asyncio.get_running_loop().time() - 2

    with (
        patch(
            "pyairtouch3.client.asyncio.open_connection",
            AsyncMock(return_value=(reader, writer)),
        ),
        patch("pyairtouch3.client.asyncio.sleep", AsyncMock()) as sleep,
    ):
        await client.send_message(bytearray(b"command"))

    sleep.assert_awaited_once()
    assert sleep.await_args.args[0] == pytest.approx(3, abs=0.01)
    assert writer.written_data == bytearray(b"command")


async def test_send_message_write_error_raises() -> None:
    """Test write errors are surfaced as AirTouchError."""
    reader = FakeStreamReader(b"")
    writer = FakeStreamWriter()
    writer.drain.side_effect = OSError("closed")

    with (
        patch(
            "pyairtouch3.client.asyncio.open_connection",
            AsyncMock(return_value=(reader, writer)),
        ),
        pytest.raises(AirTouchError),
    ):
        await AirTouchClient("1.1.1.1").send_message(bytearray(b"command"))

    assert writer.closed is True
