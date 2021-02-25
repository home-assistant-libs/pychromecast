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

from .const import CAST_TYPE_CHROMECAST, CAST_TYPES, SERVICE_TYPE_HOST

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
    except IOError:
        pass
    return _get_host_from_zc_service_info(service_info) + (service_info,)


def _get_host_from_zc_service_info(service_info: zeroconf.ServiceInfo):
    """ Get hostname or IP + port from zeroconf service_info. """
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


def _get_status(host, services, zconf, path, secure, timeout):
    """
    :param host: Hostname or ip to fetch status from
    :type host: str
    :return: The device status as a named tuple.
    :rtype: pychromecast.dial.DeviceStatus or None
    """

    if not host:
        for service in services.copy():
            host, _, _ = get_host_from_service(service, zconf)
            if host:
                _LOGGER.debug("Resolved service %s to %s", service, host)
                break

    headers = {"content-type": "application/json"}

    context = None
    if secure:
        url = FORMAT_BASE_URL_HTTPS.format(host) + path
        context = ssl.SSLContext()
        context.verify_mode = ssl.CERT_NONE
    else:
        url = FORMAT_BASE_URL_HTTP.format(host) + path

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout, context=context) as response:
        data = response.read()
    return json.loads(data.decode("utf-8"))


def get_device_status(host, services=None, zconf=None, timeout=10):
    """
    :param host: Hostname or ip to fetch status from
    :type host: str
    :return: The device status as a named tuple.
    :rtype: pychromecast.dial.DeviceStatus or None
    """

    try:
        status = _get_status(
            host, services, zconf, "/setup/eureka_info?options=detail", True, timeout
        )

        friendly_name = status.get("name", "Unknown Chromecast")
        model_name = "Unknown model name"
        manufacturer = "Unknown manufacturer"
        if "detail" in status:
            model_name = status["detail"].get("model_name", model_name)
            manufacturer = status["detail"].get("manufacturer", manufacturer)

        udn = status.get("ssdp_udn", None)

        cast_type = CAST_TYPES.get(model_name.lower(), CAST_TYPE_CHROMECAST)

        uuid = None
        if udn:
            uuid = UUID(udn.replace("-", ""))

        return DeviceStatus(friendly_name, model_name, manufacturer, uuid, cast_type)

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


def get_multizone_status(host, services=None, zconf=None, timeout=10):
    """
    :param host: Hostname or ip to fetch status from
    :type host: str
    :return: The multizone status as a named tuple.
    :rtype: pychromecast.dial.MultizoneStatus or None
    """

    try:
        status = _get_status(
            host, services, zconf, "/setup/eureka_info?params=multizone", True, timeout
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
    "DeviceStatus", ["friendly_name", "model_name", "manufacturer", "uuid", "cast_type"]
)
