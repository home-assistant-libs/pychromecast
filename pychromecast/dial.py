"""
Implements the DIAL-protocol to communicate with the Chromecast
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import socket
import ssl
import urllib.request
from uuid import UUID
from typing import Any

import zeroconf

from .const import CAST_TYPE_AUDIO, CAST_TYPE_CHROMECAST, CAST_TYPE_GROUP
from .error import ZeroConfInstanceRequired
from .models import ZEROCONF_ERRORS, CastInfo, HostServiceInfo, MDNSServiceInfo

XML_NS_UPNP_DEVICE = "{urn:schemas-upnp-org:device-1-0}"

FORMAT_BASE_URL_HTTP = "http://{}:8008"
FORMAT_BASE_URL_HTTPS = "https://{}:8443"

_LOGGER = logging.getLogger(__name__)


def get_host_from_service(
    service: HostServiceInfo | MDNSServiceInfo, zconf: zeroconf.Zeroconf | None
) -> tuple[str | None, int | None, zeroconf.ServiceInfo | None]:
    """Resolve host and port from service."""
    service_info = None

    if isinstance(service, HostServiceInfo):
        return (service.host, service.port, None)

    try:
        if not zconf:
            raise ZeroConfInstanceRequired
        service_info = zconf.get_service_info("_googlecast._tcp.local.", service.name)
        if service_info:
            _LOGGER.debug(
                "get_info_from_service resolved service %s to service_info %s",
                service,
                service_info,
            )
        else:
            _LOGGER.debug(
                "get_info_from_service failed to resolve service %s",
                service,
            )
    except ZEROCONF_ERRORS:
        # We do not catch zeroconf.NotRunningException as it's
        # an unrecoverable error.
        _LOGGER.debug("get_info_from_service raised:", exc_info=True)
    return _get_host_from_zc_service_info(service_info) + (service_info,)


def _get_host_from_zc_service_info(
    service_info: zeroconf.ServiceInfo | None,
) -> tuple[str | None, int | None]:
    """Get hostname or IP + port from zeroconf service_info."""
    host = None
    port = None
    if service_info and service_info.port:
        if len(service_info.addresses) > 0:
            host = socket.inet_ntoa(service_info.addresses[0])
        elif service_info.server is not None:
            host = service_info.server.lower()
        if host is not None:
            port = service_info.port
    return (host, port)


def _get_status(
    services: set[HostServiceInfo | MDNSServiceInfo],
    zconf: zeroconf.Zeroconf | None,
    path: str,
    secure: bool,
    timeout: float,
    context: ssl.SSLContext | None,
) -> tuple[str | None, Any]:
    """Query a cast device via http(s)."""

    for service in services.copy():
        host, _, _ = get_host_from_service(service, zconf)
        if host:
            _LOGGER.debug("Resolved service %s to %s", service, host)
            break

    headers = {"content-type": "application/json"}

    if secure:
        url = FORMAT_BASE_URL_HTTPS.format(host) + path
    else:
        url = FORMAT_BASE_URL_HTTP.format(host) + path

    has_context = bool(context)
    if secure and not has_context:
        context = get_ssl_context()

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout, context=context) as response:
        data = response.read()
    return (host, json.loads(data.decode("utf-8")))


def get_ssl_context() -> ssl.SSLContext:
    """Create an SSL context."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def get_cast_type(
    cast_info: CastInfo,
    zconf: zeroconf.Zeroconf | None = None,
    timeout: float = 30,
    context: ssl.SSLContext | None = None,
) -> CastInfo:
    """Add cast type and manufacturer to a CastInfo instance."""
    cast_type = CAST_TYPE_CHROMECAST
    manufacturer = "Unknown manufacturer"
    if cast_info.port != 8009:
        cast_type = CAST_TYPE_GROUP
        manufacturer = "Google Inc."
    else:
        host: str | None = "<unknown>"
        try:
            display_supported = True
            host, status = _get_status(
                cast_info.services,
                zconf,
                "/setup/eureka_info?params=device_info,name",
                True,
                timeout,
                context,
            )
            if "device_info" in status:
                device_info = status["device_info"]

                capabilities = device_info.get("capabilities", {})
                display_supported = capabilities.get("display_supported", True)
                manufacturer = device_info.get("manufacturer", manufacturer)

            if not display_supported:
                cast_type = CAST_TYPE_AUDIO
            _LOGGER.debug("cast type: %s, manufacturer: %s", cast_type, manufacturer)

        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            OSError,
            ValueError,
        ) as err:
            _LOGGER.warning(
                "Failed to determine cast type for host %s (%s) (services:%s)",
                host,
                err,
                cast_info.services,
            )
            cast_type = CAST_TYPE_CHROMECAST

    return CastInfo(
        cast_info.services,
        cast_info.uuid,
        cast_info.model_name,
        cast_info.friendly_name,
        cast_info.host,
        cast_info.port,
        cast_type,
        manufacturer,
    )


def get_device_info(  # pylint: disable=too-many-locals
    host: str,
    services: set[HostServiceInfo | MDNSServiceInfo] | None = None,
    zconf: zeroconf.Zeroconf | None = None,
    timeout: float = 30,
    context: ssl.SSLContext | None = None,
) -> DeviceStatus | None:
    """Return a filled in DeviceStatus object for the specified device."""

    try:
        if services is None:
            services = {HostServiceInfo(host, 8009)}

        # Try connection with SSL first, and if it fails fall back to non-SSL
        try:
            _, status = _get_status(
                services,
                zconf,
                "/setup/eureka_info?params=device_info,name",
                True,
                timeout / 2,
                context,
            )
        except (urllib.error.HTTPError, urllib.error.URLError):
            _, status = _get_status(
                services,
                zconf,
                "/setup/eureka_info?params=device_info,name",
                False,
                timeout / 2,
                context,
            )

        cast_type = CAST_TYPE_CHROMECAST
        display_supported = True
        friendly_name = status.get("name", "Unknown Chromecast")
        manufacturer = "Unknown manufacturer"
        model_name = "Unknown model name"
        multizone_supported = False
        udn = None

        if "device_info" in status:
            device_info = status["device_info"]

            capabilities = device_info.get("capabilities", {})
            display_supported = capabilities.get("display_supported", True)
            multizone_supported = capabilities.get("multizone_supported", True)
            friendly_name = device_info.get("name", friendly_name)
            model_name = device_info.get("model_name", model_name)
            manufacturer = device_info.get("manufacturer", manufacturer)
            udn = device_info.get("ssdp_udn", None)
        else:
            udn = status.get("ssdp_udn", None)

        if not display_supported:
            cast_type = CAST_TYPE_AUDIO

        uuid = None
        if udn:
            uuid = UUID(udn.replace("-", ""))

        return DeviceStatus(
            friendly_name,
            model_name,
            manufacturer,
            uuid,
            cast_type,
            multizone_supported,
        )

    except (urllib.error.HTTPError, urllib.error.URLError, OSError, ValueError):
        return None


def _get_group_info(host: str, group: Any) -> MultizoneInfo:
    """Parse group JSON data and return a MultizoneInfo instance."""
    name = group.get("name", "Unknown group name")
    udn = group.get("uuid", None)
    uuid = None
    if udn:
        uuid = UUID(udn.replace("-", ""))
    elected_leader = group.get("elected_leader", "")
    elected_leader_split = elected_leader.rsplit(":", 1)

    leader_host = None
    leader_port = None
    if elected_leader == "self" and "cast_port" in group:
        leader_host = host
        leader_port = group["cast_port"]
    elif len(elected_leader_split) == 2:
        # The port in the URL is not useful, but we can scan the host
        leader_host = elected_leader_split[0]

    return MultizoneInfo(name, uuid, leader_host, leader_port)


def get_multizone_status(
    host: str,
    services: set[HostServiceInfo | MDNSServiceInfo] | None = None,
    zconf: zeroconf.Zeroconf | None = None,
    timeout: float = 30,
    context: ssl.SSLContext | None = None,
) -> MultizoneStatus | None:
    """Return a filled in MultizoneStatus object for the specified device."""

    try:
        if services is None:
            services = {HostServiceInfo(host, 8009)}
        _, status = _get_status(
            services,
            zconf,
            "/setup/eureka_info?params=multizone",
            True,
            timeout,
            context,
        )

        dynamic_groups = []
        if "multizone" in status and "dynamic_groups" in status["multizone"]:
            for group in status["multizone"]["dynamic_groups"]:
                dynamic_groups.append(_get_group_info(host, group))

        groups = []
        if "multizone" in status and "groups" in status["multizone"]:
            for group in status["multizone"]["groups"]:
                groups.append(_get_group_info(host, group))

        return MultizoneStatus(dynamic_groups, groups)

    except (urllib.error.HTTPError, urllib.error.URLError, OSError, ValueError):
        return None


@dataclass(frozen=True)
class MultizoneInfo:
    """Multizone info container."""

    friendly_name: str
    uuid: UUID | None
    host: str | None
    port: int | None


@dataclass(frozen=True)
class MultizoneStatus:
    """Multizone status container."""

    dynamic_groups: list[MultizoneInfo]
    groups: list[MultizoneInfo]


@dataclass(frozen=True)
class DeviceStatus:
    """Device status container."""

    friendly_name: str
    model_name: str
    manufacturer: str
    uuid: UUID | None
    cast_type: str
    multizone_supported: bool
