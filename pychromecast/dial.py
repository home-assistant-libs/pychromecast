"""
Implements the DIAL-protocol to communicate with the Chromecast
"""
from collections import namedtuple
import json
import logging
import ssl
import urllib.request
from uuid import UUID

from .const import CAST_TYPE_CHROMECAST, CAST_TYPES
from .discovery import get_info_from_service, get_host_from_service_info

XML_NS_UPNP_DEVICE = "{urn:schemas-upnp-org:device-1-0}"

FORMAT_BASE_URL_HTTP = "http://{}:8008"
FORMAT_BASE_URL_HTTPS = "https://{}:8443"

_LOGGER = logging.getLogger(__name__)


def _get_status(host, services, zconf, path, secure=False):
    """
    :param host: Hostname or ip to fetch status from
    :type host: str
    :return: The device status as a named tuple.
    :rtype: pychromecast.dial.DeviceStatus or None
    """

    if not host:
        for service in services.copy():
            service_info = get_info_from_service(service, zconf)
            host, _ = get_host_from_service_info(service_info)
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
    with urllib.request.urlopen(req, timeout=10, context=context) as response:
        data = response.read()
    return json.loads(data.decode("utf-8"))


def get_device_status(host, services=None, zconf=None):
    """
    :param host: Hostname or ip to fetch status from
    :type host: str
    :return: The device status as a named tuple.
    :rtype: pychromecast.dial.DeviceStatus or None
    """

    try:
        status = _get_status(
            host, services, zconf, "/setup/eureka_info?options=detail", secure=True
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


def get_multizone_status(host, services=None, zconf=None):
    """
    :param host: Hostname or ip to fetch status from
    :type host: str
    :return: The multizone status as a named tuple.
    :rtype: pychromecast.dial.MultizoneStatus or None
    """

    try:
        status = _get_status(
            host, services, zconf, "/setup/eureka_info?params=multizone", secure=True
        )

        dynamic_groups = []
        if "multizone" in status and "dynamic_groups" in status["multizone"]:
            for group in status["multizone"]["dynamic_groups"]:
                name = group.get("name", "Unknown group name")
                udn = group.get("uuid", None)
                uuid = None
                if udn:
                    uuid = UUID(udn.replace("-", ""))
                dynamic_groups.append(MultizoneInfo(name, uuid))

        groups = []
        if "multizone" in status and "groups" in status["multizone"]:
            for group in status["multizone"]["groups"]:
                name = group.get("name", "Unknown group name")
                udn = group.get("uuid", None)
                uuid = None
                if udn:
                    uuid = UUID(udn.replace("-", ""))
                groups.append(MultizoneInfo(name, uuid))

        return MultizoneStatus(dynamic_groups, groups)

    except (urllib.error.HTTPError, urllib.error.URLError, OSError, ValueError):
        return None


MultizoneInfo = namedtuple("MultizoneInfo", ["friendly_name", "uuid"])

MultizoneStatus = namedtuple("MultizoneStatus", ["dynamic_groups", "groups"])

DeviceStatus = namedtuple(
    "DeviceStatus", ["friendly_name", "model_name", "manufacturer", "uuid", "cast_type"]
)
