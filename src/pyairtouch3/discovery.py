"""UDP discovery helpers for AirTouch 3 controllers."""

import asyncio
from dataclasses import dataclass
import ipaddress
import logging
import socket

_LOGGER = logging.getLogger(__name__)

DISCOVERY_ATTEMPTS = 2
DISCOVERY_MESSAGE = b"HF-A11ASSISTHREAD"
DISCOVERY_PORT = 49003
DISCOVERY_SEND_INTERVAL = 0.5


@dataclass(slots=True, frozen=True)
class AirTouch3Discovery:
    """Discovered AirTouch 3 controller."""

    host: str
    mac: str
    model: str


def parse_discovery_payload(data: bytes) -> AirTouch3Discovery | None:
    """Parse an AirTouch 3 UDP discovery reply."""
    try:
        payload = data.decode("ascii").strip("\x00\r\n ")
    except UnicodeDecodeError:
        return None

    parts = [part.strip() for part in payload.split(",")]
    if len(parts) != 3:
        return None

    host, mac, model = parts
    if model != "AirTouch3":
        return None

    try:
        ipaddress.IPv4Address(host)
    except ipaddress.AddressValueError:
        return None

    return AirTouch3Discovery(host=host, mac=mac, model=model)


async def async_discover_targets(
    targets: list[str],
    timeout: float,
    *,
    port: int = DISCOVERY_PORT,
    attempts: int = DISCOVERY_ATTEMPTS,
    send_interval: float = DISCOVERY_SEND_INTERVAL,
    bind_host: str = "",
    logger: logging.Logger | None = None,
) -> list[AirTouch3Discovery]:
    """Discover AirTouch 3 controllers by sending UDP requests to target hosts."""
    log = logger or _LOGGER
    if not targets:
        return []

    log.debug(
        "Starting AirTouch 3 discovery on UDP port %s with targets: %s",
        port,
        ", ".join(targets),
    )
    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setblocking(False)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((bind_host, port))
    except OSError as err:
        sock.close()
        log.debug("Unable to bind AirTouch 3 discovery socket: %s", err)
        return []

    log.debug("AirTouch 3 discovery socket bound to %s", sock.getsockname())
    discoveries: dict[str, AirTouch3Discovery] = {}
    try:
        for attempt in range(attempts):
            log.debug(
                "Sending AirTouch 3 discovery request %s/%s",
                attempt + 1,
                attempts,
            )
            for target in targets:
                try:
                    await loop.sock_sendto(sock, DISCOVERY_MESSAGE, (target, port))
                    log.debug(
                        "Sent AirTouch 3 discovery request to %s:%s",
                        target,
                        port,
                    )
                except OSError as err:
                    log.debug("AirTouch 3 discovery send to %s failed: %s", target, err)
            if attempt < attempts - 1:
                await asyncio.sleep(send_interval)

        log.debug("Listening for AirTouch 3 discovery replies for %s seconds", timeout)
        deadline = loop.time() + timeout
        while (remaining := deadline - loop.time()) > 0:
            try:
                data, addr = await asyncio.wait_for(
                    loop.sock_recvfrom(sock, 512), remaining
                )
            except TimeoutError:
                break
            except OSError as err:
                log.debug("AirTouch 3 discovery receive failed: %s", err)
                break

            if data == DISCOVERY_MESSAGE:
                log.debug(
                    "Ignoring AirTouch 3 discovery echo from %s:%s",
                    addr[0],
                    addr[1],
                )
                continue

            if discovery := parse_discovery_payload(data):
                log.debug(
                    "Discovered AirTouch 3 controller at %s from %s:%s "
                    "(mac=%s, model=%s)",
                    discovery.host,
                    addr[0],
                    addr[1],
                    discovery.mac,
                    discovery.model,
                )
                discoveries[discovery.host] = discovery
                continue

            log.debug(
                "Ignoring non-AirTouch 3 discovery payload from %s:%s: %r",
                addr[0],
                addr[1],
                data,
            )
    finally:
        sock.close()

    log.debug(
        "AirTouch 3 discovery finished; found %s controller(s): %s",
        len(discoveries),
        ", ".join(discoveries) or "none",
    )
    return list(discoveries.values())
