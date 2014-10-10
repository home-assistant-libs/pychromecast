"""
PyChromecast: remote control your Chromecast
"""
from __future__ import print_function

from collections import namedtuple
import threading
import logging

# pylint: disable=wildcard-import
from .config import *
from .error import *
from . import socket_client
from .upnp import discover_chromecasts
from .dial import get_device_status, reboot
from .controllers.media import STREAM_TYPE_BUFFERED


def _get_all_chromecasts():
    """
    Returns a list of all chromecasts on the network as PyChromecast
    objects.
    """
    ips = discover_chromecasts()
    cc_list = []
    for ip_address in ips:
        try:
            cc_list.append(Chromecast(host=ip_address))
        except ChromecastConnectionError:
            pass
    return cc_list


def get_chromecasts(**filters):
    """
    Searches the network and returns a list of Chromecast objects.
    Filter is a list of options to filter the chromecasts by.

    ex: get_chromecasts(friendly_name="Living Room")

    May return an empty list if no chromecasts were found matching
    the filter criteria

    Filters include DeviceStatus items:
        friendly_name, model_name, manufacturer, api_version
    Or AppStatus items:
        app_id, description, state, service_url, service_protocols (list)
    Or ip address:
        ip
    """
    cc_list = set(_get_all_chromecasts())
    excluded_cc = set()

    if not filters:
        return list(cc_list)

    if 'ip' in filters:
        for chromecast in cc_list:
            if chromecast.host != filter['ip']:
                excluded_cc.add(chromecast)
        filters.pop('ip')

    for key, val in filters.items():
        for chromecast in cc_list:
            for tup in [chromecast.device, chromecast.app]:
                if hasattr(tup, key) and val != getattr(tup, key):
                    excluded_cc.add(chromecast)

    filtered_cc = cc_list - excluded_cc
    return list(filtered_cc)


def get_chromecasts_as_dict(**filters):
    """
    Returns a dictionary of chromecasts with the friendly name as
    the key.  The value is the pychromecast object itself.
    """
    # pylint: disable=star-args
    return {cc.device.friendly_name: cc for cc in get_chromecasts(**filters)}


def get_chromecast(strict=False, **filters):
    """
    Same as get_chromecasts but only if filter matches exactly one
    ChromeCast.

    Returns a Chromecast matching exactly the fitler specified.

    If strict, return one and only one chromecast
    """

    # If we have filters or are operating in strict mode we have to scan
    # for all Chromecasts to ensure there is only 1 matching chromecast.
    # If no filters given and not strict just use the first dicsovered one.
    if filters or strict:
        results = get_chromecasts(**filters)
    else:
        results = [Chromecast(ip) for ip in discover_chromecasts(1)]

    if len(results) > 1:
        if strict:
            raise MultipleChromecastsFoundError(
                'More than one Chromecast was found specifying '
                'the filter criteria: {}'.format(filters))
        else:
            return results[0]

    elif not results:
        if strict:
            raise NoChromecastFoundError(
                'No Chromecasts matching filter critera were found:'
                ' {}'.format(filters))
        else:
            return None

    else:
        return results[0]


# pylint: disable=too-many-instance-attributes
class Chromecast(object):
    """ Class to interface with a ChromeCast. """

    def __init__(self, host):
        self.logger = logging.getLogger(__name__)

        self.host = host

        self.logger.info("Querying device status")
        self.device = get_device_status(self.host)

        if not self.device:
            raise ChromecastConnectionError(
                "Could not connect to {}".format(self.host))

        self.status = None
        self.media_status = None

        self.socket_client = socket_client.SocketClient(host)

        self.socket_client.receiver_controller.register_status_listener(self)

        # Forward these method
        self.play_media = self.socket_client.media_controller.play_media
        self.register_handler = self.socket_client.register_handler

        self.socket_client.start()

    @property
    def is_idle(self):
        """ Returns if there is currently an app running. """
        return self.status is None or self.status.app_id == APP_BACKDROP

    @property
    def app_id(self):
        """ Returns the current app_id. """
        return self.status.app_id if self.status else None

    @property
    def app_display_name(self):
        """ Returns the name of the current running app. """
        return self.status.display_name if self.status else None

    @property
    def media_controller(self):
        """ Returns the media controller. """
        return self.socket_client.media_controller

    def new_cast_status(self, status):
        """ Called when a new status received from the Chromecast. """
        self.status = status

    def start_app(self, app_id):
        """ Start an app on the Chromecast. """
        self.logger.info("Starting app {}".format(app_id))

        self.socket_client.receiver_controller.launch_app(app_id)

    def quit_app(self):
        """ Tells the Chromecast to quit current app_id. """
        self.logger.info("Quiting current app")

        self.socket_client.receiver_controller.stop_app()

    def reboot(self):
        """ Reboots the Chromecast. """
        reboot(self.host)

    def __del__(self):
        self.socket_client.stop.set()

    def __repr__(self):
        return "Chromecast({}, {}, {}, {}, api={}.{})".format(
            self.host, self.device.friendly_name, self.device.model_name,
            self.device.manufacturer, self.device.api_version[0],
            self.device.api_version[1])
