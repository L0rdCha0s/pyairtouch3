"""Python client for AirTouch 3 controllers."""

from .airtouch_aircon import Aircon
from .airtouch_message import AirTouchMessage
from .airtouch_sensor import Sensor
from .airtouch_zone import AirtouchZone
from .client import DEFAULT_PORT, RESPONSE_TIMEOUT, AirTouchClient, AirTouchError
from .discovery import (
    DISCOVERY_ATTEMPTS,
    DISCOVERY_MESSAGE,
    DISCOVERY_PORT,
    DISCOVERY_SEND_INTERVAL,
    AirTouch3Discovery,
    async_discover_targets,
    parse_discovery_payload,
)
from .enums import AcMode, ZoneStatus
from .message_constants import MessageConstants
from .message_response_parser import MessageResponseParser

__all__ = [
    "DEFAULT_PORT",
    "DISCOVERY_ATTEMPTS",
    "DISCOVERY_MESSAGE",
    "DISCOVERY_PORT",
    "DISCOVERY_SEND_INTERVAL",
    "RESPONSE_TIMEOUT",
    "AcMode",
    "AirTouch3Discovery",
    "AirTouchClient",
    "AirTouchError",
    "AirTouchMessage",
    "Aircon",
    "AirtouchZone",
    "MessageConstants",
    "MessageResponseParser",
    "Sensor",
    "ZoneStatus",
    "async_discover_targets",
    "parse_discovery_payload",
]
