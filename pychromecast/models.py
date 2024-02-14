"""
Chromecast types
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID

import zeroconf

ZEROCONF_ERRORS: tuple[type[Exception], ...] = (IOError, asyncio.TimeoutError)
if hasattr(zeroconf, "EventLoopBlocked"):
    # Added in zeroconf 0.37.0
    ZEROCONF_ERRORS = (*ZEROCONF_ERRORS, zeroconf.EventLoopBlocked)


@dataclass(frozen=True)
class CastInfo:
    """Cast info container."""

    services: set[HostServiceInfo | MDNSServiceInfo]
    uuid: UUID
    model_name: str | None
    friendly_name: str | None
    host: str
    port: int
    cast_type: str | None
    manufacturer: str | None


@dataclass(frozen=True)
class HostServiceInfo:
    """Service info container."""

    host: str
    port: int


@dataclass(frozen=True)
class MDNSServiceInfo:
    """Service info container."""

    name: str
