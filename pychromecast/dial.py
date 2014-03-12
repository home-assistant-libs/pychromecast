"""
Implements the DIAL-protocol to communicate with the Chromecast
"""
import xml.etree.ElementTree as ET
from collections import namedtuple

import requests


XML_NS_UPNP_DEVICE = "{urn:schemas-upnp-org:device-1-0}"
XML_NS_DIAL = "{urn:dial-multiscreen-org:schemas:dial}"
XML_NS_CAST = "{urn:chrome.google.com:cast}"

FORMAT_BASE_URL = "http://{}:8008"
FORMAT_APP_PATH = FORMAT_BASE_URL + "/apps/{}"

CC_SESSION = requests.Session()
CC_SESSION.headers['content-type'] = 'application/json'


def start_app(host, app_id, data=None):
    """ Starts an application.

        If your TV is not on will turn it on unless app_id == APP_ID_HOME. """

    if data is None:
        data = {"": ""}

    CC_SESSION.post(_craft_app_url(host, app_id), data=data)


def quit_app(host, app_id=None):
    """ Quits specified application if it is running.
        If no app_id specified will quit current running app. """

    if not app_id:
        status = get_app_status(host)

        if status:
            app_id = status.app_id

    if app_id:
        CC_SESSION.delete(_craft_app_url(host, app_id))


def reboot(host):
    """ Reboots the chromecast. """
    CC_SESSION.post(FORMAT_BASE_URL.format(host) + "/setup/reboot",
                    data='{"params":"now"}')


def get_device_status(host):
    """ Returns the device status as a named tuple. """

    try:
        req = CC_SESSION.get(
            FORMAT_BASE_URL.format(host) + "/ssdp/device-desc.xml")

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


def get_app_status(host, app_id=None):
    """ Returns the status of the specified app
        or else the current running app. """
    # /apps/ will redirect to the active app
    url = (FORMAT_APP_PATH.format(host, app_id) if app_id
           else FORMAT_BASE_URL.format(host) + "/apps/")

    try:
        req = CC_SESSION.get(url)

        if req.status_code == 204:
            return None

        status_el = ET.fromstring(req.text.encode("UTF-8"))
        options = status_el.find(XML_NS_DIAL + "options").attrib

        app_id = _read_xml_element(status_el, XML_NS_DIAL,
                                   "name", "Unknown application")

        state = _read_xml_element(status_el, XML_NS_DIAL,
                                  "state", "unknown")

        service_el = status_el.find(XML_NS_CAST + "servicedata")

        if service_el is not None:
            service_url = _read_xml_element(service_el, XML_NS_CAST,
                                            "connectionSvcURL", None)

            protocols_el = service_el.find(XML_NS_CAST + "protocols")

            if protocols_el is not None:
                protocols = [el.text for el in protocols_el]
            else:
                protocols = []

        else:
            service_url = None
            protocols = []

        activity_el = status_el.find(XML_NS_CAST + "activity-status")

        if activity_el is not None:
            description = _read_xml_element(activity_el, XML_NS_CAST,
                                            "description", app_id)
        else:
            description = app_id

        return AppStatus(app_id, description, state,
                         options, service_url, protocols)

    except (requests.exceptions.RequestException, ET.ParseError):
        return None


def _craft_app_url(host, app_id=None):
    """ Helper method to create a ChromeCast url given
        a host and an optional app_id. """
    return (FORMAT_APP_PATH.format(host, app_id) if app_id
            else FORMAT_BASE_URL.format(host))


def _read_xml_element(element, xml_ns, tag_name, default=""):
    """ Helper method to read text from an element. """
    try:
        return element.find(xml_ns + tag_name).text

    except AttributeError:
        return default


DeviceStatus = namedtuple("DeviceStatus",
                          ["friendly_name", "model_name",
                           "manufacturer", "api_version"])

AppStatus = namedtuple("AppStatus", ["app_id", "description", "state",
                                     "options", "service_url",
                                     "service_protocols"])
