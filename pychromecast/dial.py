"""
Implements the DIAL-protocol to communicate with the Chromecast
"""
from collections import namedtuple
from uuid import UUID

import logging
import requests

from .const import CAST_TYPE_CHROMECAST
from .discovery import get_info_from_service, get_host_from_service_info

XML_NS_UPNP_DEVICE = "{urn:schemas-upnp-org:device-1-0}"

FORMAT_BASE_URL = "http://{}:8008"

_LOGGER = logging.getLogger(__name__)


def reboot(host):
    """ Reboots the chromecast. """
    headers = {"content-type": "application/json"}

    requests.post(
        FORMAT_BASE_URL.format(host) + "/setup/reboot",
        data='{"params":"now"}',
        headers=headers,
        timeout=10,
    )


def _get_status(host, services, zconf, path):
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

    req = requests.get(FORMAT_BASE_URL.format(host) + path, headers=headers, timeout=10)

    req.raise_for_status()

    # The Requests library will fall back to guessing the encoding in case
    # no encoding is specified in the response headers - which is the case
    # for the Chromecast.
    # The standard mandates utf-8 encoding, let's fall back to that instead
    # if no encoding is provided, since the autodetection does not always
    # provide correct results.
    if req.encoding is None:
        req.encoding = "utf-8"

    return req.json()


def get_device_status(host, services=None, zconf=None):
    """
    :param host: Hostname or ip to fetch status from
    :type host: str
    :return: The device status as a named tuple.
    :rtype: pychromecast.dial.DeviceStatus or None
    """

    try:
        status = _get_status(host, services, zconf, "/setup/eureka_info?options=detail")

        friendly_name = status.get("name", "Unknown Chromecast")
        # model_name and manufacturer is no longer included in the response,
        # mark as unknown
        model_name = "Unknown model name"
        manufacturer = "Unknown manufacturer"

        udn = status.get("ssdp_udn", None)

        cast_type = CAST_TYPE_CHROMECAST

        uuid = None
        if udn:
            uuid = UUID(udn.replace("-", ""))

        return DeviceStatus(friendly_name, model_name, manufacturer, uuid, cast_type)

    except (requests.exceptions.RequestException, OSError, ValueError):
        return None


DeviceStatus = namedtuple(
    "DeviceStatus", ["friendly_name", "model_name", "manufacturer", "uuid", "cast_type"]
)
