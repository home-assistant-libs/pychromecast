"""
PyChromecast: remote control your Chromecast
"""
from collections import namedtuple
import threading
import logging

from .config import APP_ID, get_possible_app_ids, get_app_config
from .upnp import discover_chromecasts
from .dial import start_app, quit_app, get_device_status, get_app_status
from .websocket import (PROTOCOL_RAMP, RAMP_ENABLED, RAMP_STATE_UNKNOWN,
                        RAMP_STATE_PLAYING, RAMP_STATE_STOPPED,
                        create_websocket_client)
from .error import (
    PyChromecastError,
    NoChromecastFoundError,
    MultipleChromecastsFoundError,
    ConnectionError,
    )


def play_youtube_video(video_id, host=None):
    """ Starts the YouTube app if it is not running and plays
        specified video. """

    host = get_chromecast(strict=False, ip=host).host
    start_app(host, APP_ID["YOUTUBE"], {"v": video_id})


def play_youtube_playlist(playlist_id, host=None):
    """ Starts the YouTube app if it is not running and plays
        specified playlist. """

    host = get_chromecast(strict=False, ip=host).host
    start_app(host, APP_ID["YOUTUBE"],
              {"listType": "playlist", "list": playlist_id})


def _get_all_chromecasts():
    """
    Returns a list of all chromecasts on the network as PyChromecast
    objects.
    """
    ips = discover_chromecasts()
    cc_list = []
    for ip_address in ips:
        try:
            cc_list.append(PyChromecast(host=ip_address))
        except ConnectionError:
            pass
    return cc_list


def get_chromecasts(**filters):
    """
    Return the set of chromecasts as PyChromecast Objects
    filter is a list of options to filter the chromecasts by.

    ex:  filter_chromecasts(friendly_name = "Living Room")

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
                if hasattr(tup, key):
                    if val != getattr(tup, key):
                        excluded_cc.add(chromecast)

    filtered_cc = cc_list - excluded_cc
    return list(filtered_cc)


def get_chromecasts_as_dict(**filters):
    """
    Returns a dictionary of chromecasts with the friendly name as
    the key.  The value is the pychromecast object itself.
    """
    cc_list = get_chromecasts(**filters)
    cc_dict = {cc.device.friendly_name: cc for cc in cc_list}
    return cc_dict


def get_chromecast(strict=True, **filters):
    """
    Same as get_chromecasts but only if filter matches exactly one
    ChromeCast

    Returns a Chromecast matching exactly the fitler specified.

    If strict, return one and only one chromecast
    """
    results = get_chromecasts(**filters)
    if len(results) > 1:
        if strict:
            raise MultipleChromecastsFoundError(
                'More than one Chromecast was found specifying '
                'the filter criteria: {}'.format(filters))
        else:
            return results[0]
    elif not results:
        raise NoChromecastFoundError(
            'No Chromecasts matching filter critera were found:'
            ' {}'.format(filters))
    else:
        return results[0]


class PyChromecast(object):
    """ Class to interface with a ChromeCast. """

    def __init__(self, host):
        self.logger = logging.getLogger(__name__)

        self.host = host

        self.logger.info("Querying device status")
        self.device = get_device_status(self.host)

        if not self.device:
            raise ConnectionError("Could not connect to {}".format(self.host))

        self.app = None
        self.websocket_client = None
        self._refresh_timer = None
        self._refresh_lock = threading.Lock()

        self.refresh()

    @property
    def app_id(self):
        """ Returns the current app_id. """
        return self.app.app_id if self.app else None

    @property
    def app_description(self):
        """ Returns the name of the current running app. """
        return self.app.description if self.app else None

    def get_protocol(self, protocol):
        """ Returns the current RAMP content info and controls. """
        if self.websocket_client:
            return self.websocket_client.handlers.get(protocol)
        else:
            return None

    def refresh(self):
        """
        Queries the Chromecast for the current status.
        Starts a websocket client if possible.
        """
        self.logger.info("Refreshing app status")

        # If we are refreshing but a refresh was planned, cancel that one
        with self._refresh_lock:
            if self._refresh_timer:
                self._refresh_timer.cancel()
                self._refresh_timer = None

        cur_app = self.app
        cur_ws = self.websocket_client

        self.app = app = get_app_status(self.host)

        # If no previous app and no new app there is nothing to do
        if not cur_app and not app:
            is_diff_app = False
        else:
            is_diff_app = (not cur_app and app or cur_app and not app or
                           cur_app.app_id != app.app_id)

        # Clean up websocket if:
        #  - there is a different app and a connection exists
        #  - if it is the same app but the connection is terminated
        if cur_ws and (is_diff_app or cur_ws.terminated):

            if not cur_ws.terminated:
                cur_ws.close_connection()

            self.websocket_client = cur_ws = None

        # Create a new websocket client if there is no connection
        if not cur_ws and app:

            try:
                # If the current app is not capable of a websocket client
                # This method will return None so nothing is lost
                self.websocket_client = cur_ws = create_websocket_client(app)

            except ConnectionError:
                pass

            # Ramp service does not always immediately show up in the app
            # status. If we do not have a websocket client but the app is
            # known to be RAMP controllable, then plan refresh.
            if not cur_ws and app.app_id in RAMP_ENABLED:
                self._delayed_refresh()

    def start_app(self, app_id, data=None):
        """ Start an app on the Chromecast. """
        self.logger.info("Starting app {}".format(app_id))

        # data parameter has to contain atleast 1 key
        # or else some apps won't show
        start_app(self.host, app_id, data)

        self._delayed_refresh()

    def quit_app(self):
        """ Tells the Chromecast to quit current app_id. """
        self.logger.info("Quiting current app")

        quit_app(self.host)

        self._delayed_refresh()

    def _delayed_refresh(self):
        """ Give the ChromeCast time to start the app, then refresh app. """
        with self._refresh_lock:
            if self._refresh_timer:
                self._refresh_timer.cancel()

            self._refresh_timer = threading.Timer(5, self.refresh)
            self._refresh_timer.daemon = True
            self._refresh_timer.start()

    def __str__(self):
        return "PyChromecast({}, {}, {}, {}, api={}.{})".format(
            self.host, self.device.friendly_name, self.device.model_name,
            self.device.manufacturer, self.device.api_version[0],
            self.device.api_version[1])
