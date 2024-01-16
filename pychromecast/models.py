"""
Chromecast types
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID

import zeroconf

ZEROCONF_ERRORS = (IOError, asyncio.TimeoutError)
if hasattr(zeroconf, "EventLoopBlocked"):
    # Added in zeroconf 0.37.0
    ZEROCONF_ERRORS = (*ZEROCONF_ERRORS, zeroconf.EventLoopBlocked)


@dataclass(frozen=True)
class CastInfo:
    """Cast info container."""

    services: list[ServiceInfo]
    uuid: UUID
    model_name: str | None
    friendly_name: str | None
    host: str
    port: int
    cast_type: str | None
    manufacturer: str | None


@dataclass(frozen=True)
class ServiceInfo:
    """Service info container."""

    type: str
    data: tuple[str, int] | str
