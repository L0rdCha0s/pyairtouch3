"""Async TCP client for AirTouch 3 controllers."""

import asyncio
import contextlib
import logging

from .airtouch_aircon import Aircon
from .airtouch_message import AirTouchMessage
from .message_constants import MessageConstants
from .message_response_parser import MessageResponseParser

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 8899
RESPONSE_TIMEOUT = 10
COMMAND_INTERVAL = 5
MIN_RESPONSE_LENGTH = (
    MessageConstants.AIRTOUCH_ID_START + MessageConstants.AIRTOUCH_ID_LENGTH
)


class AirTouchError(Exception):
    """Error raised when AirTouch communication or parsing fails."""


class AirTouchClient:
    """Async client for an AirTouch 3 controller."""

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        *,
        timeout: float = RESPONSE_TIMEOUT,
        command_interval: float = COMMAND_INTERVAL,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize the client."""
        self.host = host
        self.port = port
        self.timeout = timeout
        self.command_interval = command_interval
        self._logger = logger or _LOGGER
        self._command_lock = asyncio.Lock()
        self._socket_lock = asyncio.Lock()
        self._last_command_at: float | None = None

    async def request_status(self) -> bytes:
        """Send the status request and return the raw response bytes."""
        async with self._socket_lock:
            return await self._request_status()

    async def _request_status(self) -> bytes:
        """Send the status request while the socket lock is held."""
        writer: asyncio.StreamWriter | None = None
        try:
            self._logger.debug(
                "Fetching AirTouch 3 data from %s:%s", self.host, self.port
            )
            async with asyncio.timeout(self.timeout):
                reader, writer = await asyncio.open_connection(self.host, self.port)
                writer.write(AirTouchMessage().get_init_msg())
                await writer.drain()
                return await reader.read(1024)
        except (TimeoutError, OSError) as err:
            raise AirTouchError(f"Communication error with AirTouch: {err}") from err
        finally:
            if writer:
                writer.close()
                with contextlib.suppress(OSError):
                    await writer.wait_closed()

    async def fetch_aircon(self) -> Aircon:
        """Fetch and parse the controller status."""
        response_data = await self.request_status()
        self._logger.debug(
            "Received %s bytes from AirTouch 3 controller at %s:%s",
            len(response_data),
            self.host,
            self.port,
        )
        if len(response_data) < MIN_RESPONSE_LENGTH:
            raise AirTouchError(
                f"AirTouch response was too short: {len(response_data)} bytes"
            )

        try:
            return MessageResponseParser(bytearray(response_data), self._logger).parse()
        except (ValueError, IndexError) as err:
            raise AirTouchError(f"Communication error with AirTouch: {err}") from err

    async def send_message(self, message: bytes | bytearray) -> None:
        """Send a raw AirTouch protocol message."""
        async with self._command_lock:
            loop = asyncio.get_running_loop()
            if self._last_command_at is not None:
                elapsed = loop.time() - self._last_command_at
                if (delay := self.command_interval - elapsed) > 0:
                    self._logger.debug(
                        "Waiting %.2f seconds before sending AirTouch command",
                        delay,
                    )
                    await asyncio.sleep(delay)

            try:
                async with self._socket_lock:
                    await self._send_message(message)
            finally:
                self._last_command_at = loop.time()

    async def _send_message(self, message: bytes | bytearray) -> None:
        """Send a raw AirTouch protocol message while locks are held."""
        writer: asyncio.StreamWriter | None = None
        try:
            async with asyncio.timeout(self.timeout):
                _, writer = await asyncio.open_connection(self.host, self.port)
                writer.write(message)
                await writer.drain()
        except (TimeoutError, OSError) as err:
            raise AirTouchError(f"Communication error with AirTouch: {err}") from err
        finally:
            if writer:
                writer.close()
                with contextlib.suppress(OSError):
                    await writer.wait_closed()

    async def toggle_zone(self, zone_id: int) -> None:
        """Toggle power on or off for a zone."""
        await self.send_message(AirTouchMessage().toggle_zone(zone_id))

    async def adjust_zone_temperature(self, zone_id: int, inc_dec: int) -> None:
        """Increment or decrement a zone target temperature by one step."""
        await self.send_message(AirTouchMessage().set_fan(zone_id, inc_dec))

    async def toggle_ac_power(self, ac_id: int) -> None:
        """Toggle power on or off for an AC."""
        await self.send_message(AirTouchMessage().toggle_ac_on_off(ac_id))

    async def set_mode(self, ac_id: int, brand_id: int, mode: int) -> None:
        """Set the AC mode."""
        await self.send_message(AirTouchMessage().set_mode(ac_id, brand_id, mode))

    async def set_fan_speed(self, ac_id: int, brand_id: int, speed: int) -> None:
        """Set the AC fan speed."""
        await self.send_message(AirTouchMessage().set_fan_speed(ac_id, brand_id, speed))
