"""
Implements the DIAL-protocol to communicate with the Chromecast
"""
import xml.etree.ElementTree as ET
from collections import namedtuple

import requests


XML_NS_UPNP_DEVICE = "{urn:schemas-upnp-org:device-1-0}"

FORMAT_BASE_URL = "http://{}:8008"

CC_SESSION = requests.Session()
CC_SESSION.headers['content-type'] = 'application/json'


def reboot(host):
    """ Reboots the chromecast. """
    CC_SESSION.post(FORMAT_BASE_URL.format(host) + "/setup/reboot",
                    data='{"params":"now"}', timeout=10)


def get_device_status(host):
    """ Returns the device status as a named tuple. """

    try:
        req = CC_SESSION.get(
            FORMAT_BASE_URL.format(host) + "/ssdp/device-desc.xml",
            timeout=10)

        status_el = ET.fromstring(req.text.encode("UTF-8"))

        device_info_el = status_el.find(XML_NS_UPNP_DEVICE + "device")
        api_version_el = status_el.find(XML_NS_UPNP_DEVICE + "specVersion")

        friendly_name = _read_xml_element(device_info_el, XML_NS_UPNP_DEVICE,
                                          "friendlyName", "Unknown Chromecast")
        model_name = _read_xml_element(device_info_el, XML_NS_UPNP_DEVICE,
                                       "modelName", "Unknown model name")
        manufacturer = _read_xml_element(device_info_el, XML_NS_UPNP_DEVICE,
                                         "manufacturer",
                                         "Unknown manufacturer")

        api_version = (int(_read_xml_element(api_version_el,
                                             XML_NS_UPNP_DEVICE, "major", -1)),
                       int(_read_xml_element(api_version_el,
                                             XML_NS_UPNP_DEVICE, "minor", -1)))

        return DeviceStatus(friendly_name, model_name, manufacturer,
                            api_version)

    except (requests.exceptions.RequestException, ET.ParseError):
        return None


def _read_xml_element(element, xml_ns, tag_name, default=""):
    """ Helper method to read text from an element. """
    try:
        return element.find(xml_ns + tag_name).text

    except AttributeError:
        return default


DeviceStatus = namedtuple("DeviceStatus",
                          ["friendly_name", "model_name",
                           "manufacturer", "api_version"])
