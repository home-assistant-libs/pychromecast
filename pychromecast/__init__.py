"""
PyChromecast: remote control your Chromecast
"""
from __future__ import print_function

import logging
import fnmatch

# pylint: disable=wildcard-import
from .config import *  # noqa
from .error import *  # noqa
from . import socket_client
from .discovery import discover_chromecasts
from .dial import get_device_status, reboot
from .controllers.media import STREAM_TYPE_BUFFERED  # noqa

IDLE_APP_ID = 'E8C28D3C'
IGNORE_CEC = []


def _get_all_chromecasts(tries=None):
    """
    Returns a list of all chromecasts on the network as PyChromecast
    objects.
    """
    hosts = discover_chromecasts()
    cc_list = []
    for ip_address, _ in hosts:
        try:
            cc_list.append(Chromecast(host=ip_address, tries=tries))
        except ChromecastConnectionError:
            pass
    return cc_list


def get_chromecasts(tries=None, **filters):
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

    Tries is specified if you want to limit the number of times the
    underlying socket associated with your Chromecast objects will
    retry connecting if connection is lost or it fails to connect
    in the first place.
    """
    logger = logging.getLogger(__name__)

    cc_list = set(_get_all_chromecasts(tries=tries))
    excluded_cc = set()

    if not filters:
        return list(cc_list)

    if 'ip' in filters:
        for chromecast in cc_list:
            if chromecast.host != filters['ip']:
                excluded_cc.add(chromecast)
        filters.pop('ip')

    for key, val in filters.items():
        for chromecast in cc_list:
            for tup in [chromecast.device, chromecast.status]:
                if hasattr(tup, key) and val != getattr(tup, key):
                    excluded_cc.add(chromecast)

    filtered_cc = cc_list - excluded_cc

    for cast in excluded_cc:
        logger.debug("Stopping excluded chromecast %s", cast)
        cast.socket_client.stop.set()

    return list(filtered_cc)


def get_chromecasts_as_dict(tries=None, **filters):
    """
    Returns a dictionary of chromecasts with the friendly name as
    the key.  The value is the pychromecast object itself.

    Tries is specified if you want to limit the number of times the
    underlying socket associated with your Chromecast objects will
    retry connecting if connection is lost or it fails to connect
    in the first place.
    """
    return {cc.device.friendly_name: cc
            for cc in get_chromecasts(tries=tries, **filters)}


def get_chromecast(strict=False, tries=None, **filters):
    """
    Same as get_chromecasts but only if filter matches exactly one
    ChromeCast.

    Returns a Chromecast matching exactly the fitler specified.

    If strict, return one and only one chromecast

    Tries is specified if you want to limit the number of times the
    underlying socket associated with your Chromecast objects will
    retry connecting if connection is lost or it fails to connect
    in the first place.
    """

    # If we have filters or are operating in strict mode we have to scan
    # for all Chromecasts to ensure there is only 1 matching chromecast.
    # If no filters given and not strict just use the first dicsovered one.
    if filters or strict:
        results = get_chromecasts(tries=tries, **filters)
    else:
        results = _get_all_chromecasts(tries)

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

    def __init__(self, host, tries=None):
        self.logger = logging.getLogger(__name__)

        # Resolve host to IP address
        self.host = host

        self.logger.info("Querying device status")
        self.device = get_device_status(self.host)

        if not self.device:
            raise ChromecastConnectionError(
                "Could not connect to {}".format(self.host))

        self.status = None

        self.socket_client = socket_client.SocketClient(host, tries)

        receiver_controller = self.socket_client.receiver_controller
        receiver_controller.register_status_listener(self)

        # Forward these methods
        self.set_volume = receiver_controller.set_volume
        self.set_volume_muted = receiver_controller.set_volume_muted
        self.play_media = self.socket_client.media_controller.play_media
        self.register_handler = self.socket_client.register_handler

        self.socket_client.start()

    @property
    def ignore_cec(self):
        """ Returns whether the CEC data should be ignored. """
        return self.device is not None and \
            any([fnmatch.fnmatchcase(self.device.friendly_name, pattern)
                 for pattern in IGNORE_CEC])

    @property
    def is_idle(self):
        """ Returns if there is currently an app running. """
        return (self.status is None or
                self.app_id in (None, IDLE_APP_ID) or
                (not self.status.is_active_input and not self.ignore_cec))

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
        self.logger.info("Starting app %s", app_id)

        self.socket_client.receiver_controller.launch_app(app_id)

    def quit_app(self):
        """ Tells the Chromecast to quit current app_id. """
        self.logger.info("Quiting current app")

        self.socket_client.receiver_controller.stop_app()

    def reboot(self):
        """ Reboots the Chromecast. """
        reboot(self.host)

    def volume_up(self):
        """ Increment volume by 0.1 unless it is already maxed.
        Returns the new volume.

        """
        volume = round(self.status.volume_level, 1)
        return self.set_volume(volume + 0.1)

    def volume_down(self):
        """ Decrement the volume by 0.1 unless it is already 0.
        Returns the new volume.
        """
        volume = round(self.status.volume_level, 1)
        return self.set_volume(volume - 0.1)

    def __del__(self):
        self.socket_client.stop.set()

    def __repr__(self):
        return "Chromecast({}, {}, {}, {}, api={}.{})".format(
            self.host, self.device.friendly_name, self.device.model_name,
            self.device.manufacturer, self.device.api_version[0],
            self.device.api_version[1])
