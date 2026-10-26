"""
Implements the DIAL-protocol to communicate with the Chromecast
"""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
import ipaddress
import json
import logging
import ssl
import urllib.request
import urllib.error
from urllib.parse import unquote, quote, urlsplit
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
    return get_host_from_zc_service_info(service_info) + (service_info,)


def get_host_from_zc_service_info(
    service_info: zeroconf.ServiceInfo | None,
) -> tuple[str | None, int | None]:
    """Get IP + port from zeroconf service_info.

    IPv4 addresses are preferred, zeroconf lists them before IPv6 addresses.
    """
    if not service_info or not service_info.port:
        return None, None

    addresses = service_info.parsed_scoped_addresses()
    if not addresses:
        return None, None

    return addresses[0], service_info.port


def _urlopen(url: str, timeout: float, context: ssl.SSLContext | None) -> Any:
    """Help open an URL."""
    headers = {"content-type": "application/json", "host": _url_host_header(url)}
    try:
        req = urllib.request.Request(url, headers=headers)
        return urllib.request.urlopen(req, timeout=timeout, context=context)
    except urllib.error.HTTPError as err:
        if err.code != HTTPStatus.FORBIDDEN:
            raise
        # We may be blocked because we're connecting to a hostname specified directly
        # instead of to an IP address resolved by mDNS, cast devices will reject the
        # request when the address is set to the hostname. Do another attempt with an
        # empty host header.
        # Note: This is a simplified approach to not have to deal with name resolution
        # in pychromecast. If devices reject the empty host header we need to do name
        # resolution and instead set the host header to the string version of the IP.
        _LOGGER.debug("Failed to fetch %s, retrying with empty host header", url)
        headers["host"] = ""
        req = urllib.request.Request(url, headers=headers)
        return urllib.request.urlopen(req, timeout=timeout, context=context)


def _url_encode_hostname(host: str) -> str:
    """Ensure hostname is url safe."""
    # any zone identifier must be encoded
    host = host.replace("%", quote("%"))

    # make sure ipv6 ip address is enclosed
    if host.find(":") >= 0:
        host = f"[{host}]"
    return host


def _url_host_header(url: str) -> str:
    """Construct host header from url

    This is needed since urllib.request will mis-construct urls
    that contain ipv6 addresses with zone identifiers and retain
    the scope.
    """
    parsed = urlsplit(url)
    hostname, _, _ = unquote(parsed.hostname or "").partition("%")
    hostname = _url_encode_hostname(hostname)
    if parsed.port in (80, 443, None):
        return hostname
    return f"{hostname}:{parsed.port}"


def _get_status(
    services: set[HostServiceInfo | MDNSServiceInfo],
    zconf: zeroconf.Zeroconf | None,
    path: str,
    secure: bool,
    timeout: float,
    context: ssl.SSLContext | None,
) -> tuple[str | None, Any]:
    """Query a cast device via http(s)."""

    host = None
    for service in services.copy():
        host, _, _ = get_host_from_service(service, zconf)
        if host:
            _LOGGER.debug("Resolved service %s to %s", service, host)
            break

    if not host:
        # raise same as the url open would raise on invalid host
        raise urllib.error.URLError(f"Unable to resolve host for services {services}")

    host_encoded = _url_encode_hostname(host)

    if secure:
        url = FORMAT_BASE_URL_HTTPS.format(host_encoded) + path
    else:
        url = FORMAT_BASE_URL_HTTP.format(host_encoded) + path

    has_context = bool(context)
    if secure and not has_context:
        context = get_ssl_context()

    with _urlopen(url, timeout, context) as response:
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
        try:
            display_supported = True
            # Try connection with SSL first, and if it fails fall back to non-SSL
            try:
                _, status = _get_status(
                    cast_info.services,
                    zconf,
                    "/setup/eureka_info?params=device_info,name",
                    True,
                    timeout / 2,
                    context,
                )
            except (urllib.error.HTTPError, urllib.error.URLError):
                _, status = _get_status(
                    cast_info.services,
                    zconf,
                    "/setup/eureka_info?params=device_info,name",
                    False,
                    timeout / 2,
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
                cast_info.host,
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

    except (urllib.error.HTTPError, urllib.error.URLError, OSError, ValueError) as err:
        _LOGGER.debug("Failed to get device info for %s: %s (%s)", host, err, type(err))
        return None


def _inherit_scope(address: str, scoped_address: str) -> str:
    """Give a link local address the scope of scoped_address.

    A link local address is only reachable through the interface in its scope.
    Group members share a link, so the scope of the polled device applies. A
    scope reported by the device is local to the device and is dropped.
    """
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return address
    if not isinstance(ip, ipaddress.IPv6Address) or not ip.is_link_local:
        return address
    address, _, _ = address.partition("%")
    try:
        scoped_ip = ipaddress.ip_address(scoped_address)
    except ValueError:
        return address
    if isinstance(scoped_ip, ipaddress.IPv6Address) and scoped_ip.scope_id:
        return f"{address}%{scoped_ip.scope_id}"
    return address


def _get_leader_host(elected_leader: str) -> str | None:
    """Get the host from an elected leader in url host:port format."""
    try:
        hostname = urlsplit(f"//{elected_leader}").hostname
    except ValueError:
        _LOGGER.debug("Invalid elected leader %s", elected_leader)
        return None
    return unquote(hostname) if hostname else None


def _get_group_info(host: str, group: Any) -> MultizoneInfo:
    """Parse group JSON data and return a MultizoneInfo instance."""
    name = group.get("name", "Unknown group name")
    udn = group.get("uuid", None)
    uuid = None
    if udn:
        uuid = UUID(udn.replace("-", ""))
    elected_leader = group.get("elected_leader", "")

    leader_host = None
    leader_port = None
    if elected_leader == "self" and "cast_port" in group:
        leader_host = host
        leader_port = group["cast_port"]
    elif ":" in elected_leader:
        # The port in the URL is not useful, but we can scan the host
        leader_host = _get_leader_host(elected_leader)
        if leader_host:
            leader_host = _inherit_scope(leader_host, host)

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

    except (urllib.error.HTTPError, urllib.error.URLError, OSError, ValueError) as err:
        _LOGGER.debug(
            "Failed to get multizone status for %s: %s (%s)", host, err, type(err)
        )
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
