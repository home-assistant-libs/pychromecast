"""
PyChromecast: remote control your Chromecast
"""
from collections import namedtuple
import threading
import logging
import json
import requests

from .upnp import discover_chromecasts
from .dial import start_app, quit_app, get_device_status, get_app_status
from .websocket import (PROTOCOL_RAMP, RAMP_ENABLED, RAMP_STATE_UNKNOWN,
                        RAMP_STATE_PLAYING, RAMP_STATE_STOPPED,
                        create_websocket_client)
from .error import ConnectionError, NoChromecastFoundError

APP_ID = {
    "HOME": "00000000-0000-0000-0000-000000000000",
    "YOUTUBE": "YouTube",
    "NETFLIX": "Netflix",
    "TICTACTOE": "TicTacToe",
    "GOOGLE_MUSIC": "GoogleMusic",
    "PLAY_MOVIES": "PlayMovies",
    "HULU_PLUS": "Hulu_Plus",
    "HBO": "HBO_App",
    "PANDORA": "Pandora_App",
    "REDBULLTV": "edaded98-5119-4c8a-afc1-de722da03562",
    "VIKI": "1812335e-441c-4e1e-a61a-312ca1ead90e",
    "PLEX_QA": "06ee44ee-e7e3-4249-83b6-f5d0b6f07f34",
    "PLEX": "06ee44ee-e7e3-4249-83b6-f5d0b6f07f34_1",
    "VEVO": "2be788b9-b7e0-4743-9069-ea876d97ac20",
    "AVIA": "aa35235e-a960-4402-a87e-807ae8b2ac79",
    "REVISION3": "Revision3_App",
    "SONGZA": "Songza_App",
    "REALPLAYER_CLOUD": "a7f3283b-8034-4506-83e8-4e79ab1ad794_2",
    "BEYONDPOD": "18a8aeaa-8e3d-4c24-b05d-da68394a3476_1",
    "WASHINGTON_POST": "Post_TV_App",
}


def get_possible_app_ids():
    """ Returns all possible app ids. """

    try:
        req = requests.get(
            "https://clients3.google.com/cast/chromecast/device/config")
        data = json.loads(req.text[4:])

        return [app['app_name'] for app in data['applications']]

    except ValueError:
        # If json fails to parse
        return []


def play_youtube_video(video_id, host=None):
    """ Starts the YouTube app if it is not running and plays
        specified video. """

    if not host:
        host = _auto_select_chromecast()

    start_app(host, APP_ID["YOUTUBE"], {"v": video_id})


def play_youtube_playlist(playlist_id, host=None):
    """ Starts the YouTube app if it is not running and plays
        specified playlist. """

    if not host:
        host = _auto_select_chromecast()

    start_app(host, APP_ID["YOUTUBE"],
              {"listType": "playlist", "list": playlist_id})


def _auto_select_chromecast():
    """
    Discovers local Chromecasts and returns first one found.
    Raises exception if none can be found.
    """
    ips = discover_chromecasts(1)

    if ips:
        return ips[0]
    else:
        raise NoChromecastFoundError("Unable to detect Chromecast")


class PyChromecast(object):
    """ Class to interface with a ChromeCast. """

    def __init__(self, host=None):
        self.logger = logging.getLogger(__name__)

        self.host = host if host else _auto_select_chromecast()

        self.logger.info("Querying device status")
        self.device = get_device_status(self.host)

        if not self.device:
            raise ConnectionError("Could not connect to {}".format(host))

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
            self._refresh_timer.start()

    def __str__(self):
        return "PyChromecast({}, {}, {}, {}, api={}.{})".format(
            self.host, self.device.friendly_name, self.device.model_name,
            self.device.manufacturer, self.device.api_version[0],
            self.device.api_version[1])
