"""
Implements the DIAL-protocol to communicate with the Chromecast
"""
from collections import namedtuple
import json
import logging
import socket
import ssl
import urllib.request
from uuid import UUID

import zeroconf

from .const import (
    CAST_TYPE_AUDIO,
    CAST_TYPE_CHROMECAST,
    CAST_TYPE_GROUP,
    SERVICE_TYPE_HOST,
)
from .models import ZEROCONF_ERRORS, CastInfo, ServiceInfo

XML_NS_UPNP_DEVICE = "{urn:schemas-upnp-org:device-1-0}"

FORMAT_BASE_URL_HTTP = "http://{}:8008"
FORMAT_BASE_URL_HTTPS = "https://{}:8443"

_LOGGER = logging.getLogger(__name__)


def get_host_from_service(service, zconf):
    """Resolve host and port from service."""
    service_info = None

    if service.type == SERVICE_TYPE_HOST:
        return service.data + (None,)

    try:
        service_info = zconf.get_service_info("_googlecast._tcp.local.", service.data)
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


def _get_host_from_zc_service_info(service_info: zeroconf.ServiceInfo):
    """Get hostname or IP + port from zeroconf service_info."""
    host = None
    port = None
    if (
        service_info
        and service_info.port
        and (service_info.server or len(service_info.addresses) > 0)
    ):
        if len(service_info.addresses) > 0:
            host = socket.inet_ntoa(service_info.addresses[0])
        else:
            host = service_info.server.lower()
        port = service_info.port
    return (host, port)


def _get_status(services, zconf, path, secure, timeout, context):
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


def get_ssl_context():
    """Create an SSL context."""
    context = ssl.SSLContext()
    context.verify_mode = ssl.CERT_NONE
    return context


def get_cast_type(cast_info, zconf=None, timeout=30, context=None):
    """
    :param cast_info: cast_info
    :return: An updated cast_info with filled cast_type
    :rtype: pychromecast.models.CastInfo
    """
    cast_type = CAST_TYPE_CHROMECAST
    manufacturer = "Unknown manufacturer"
    if cast_info.port != 8009:
        cast_type = CAST_TYPE_GROUP
        manufacturer = "Google Inc."
    else:
        host = "<unknown>"
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
    host, services=None, zconf=None, timeout=30, context=None
):
    """
    :param host: Hostname or ip to fetch status from
    :type host: str
    :return: The device status as a named tuple.
    :rtype: pychromecast.dial.DeviceStatus or None
    """

    try:
        if services is None:
            services = [ServiceInfo(SERVICE_TYPE_HOST, (host, 8009))]
        _, status = _get_status(
            services,
            zconf,
            "/setup/eureka_info?params=device_info,name",
            True,
            timeout,
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


def _get_group_info(host, group):
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


def get_multizone_status(host, services=None, zconf=None, timeout=30, context=None):
    """
    :param host: Hostname or ip to fetch status from
    :type host: str
    :return: The multizone status as a named tuple.
    :rtype: pychromecast.dial.MultizoneStatus or None
    """

    try:
        if services is None:
            services = [ServiceInfo(SERVICE_TYPE_HOST, (host, 8009))]
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


MultizoneInfo = namedtuple("MultizoneInfo", ["friendly_name", "uuid", "host", "port"])

MultizoneStatus = namedtuple("MultizoneStatus", ["dynamic_groups", "groups"])

DeviceStatus = namedtuple(
    "DeviceStatus",
    [
        "friendly_name",
        "model_name",
        "manufacturer",
        "uuid",
        "cast_type",
        "multizone_supported",
    ],
)
