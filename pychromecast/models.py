"""
Chromecast types
"""
import asyncio
from collections import namedtuple

import zeroconf

ZEROCONF_ERRORS = (IOError, asyncio.TimeoutError)
if hasattr(zeroconf, "EventLoopBlocked"):
    # Added in zeroconf 0.37.0
    ZEROCONF_ERRORS = (*ZEROCONF_ERRORS, zeroconf.EventLoopBlocked)

CastInfo = namedtuple(
    "CastInfo",
    [
        "services",
        "uuid",
        "model_name",
        "friendly_name",
        "host",
        "port",
        "cast_type",
        "manufacturer",
    ],
)
ServiceInfo = namedtuple("ServiceInfo", ["type", "data"])
