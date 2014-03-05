"""
PyChromecast: remote control your Chromecast
"""
from collections import namedtuple
import threading
import logging
import json
import requests

from .dial import start_app, quit_app, get_device_status, get_app_status
from .websocket import PROTOCOL_RAMP, RAMP_ENABLED, create_websocket_client
from .error import ConnectionError

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


def play_youtube_video(host, video_id):
    """ Starts the YouTube app if it is not running and plays
        specified video. """

    start_app(host, APP_ID["YOUTUBE"], {"v": video_id})


def play_youtube_playlist(host, playlist_id):
    """ Starts the YouTube app if it is not running and plays
        specified playlist. """

    start_app(host, APP_ID["YOUTUBE"],
              {"listType": "playlist", "list": playlist_id})


class PyChromecast(object):
    """ Class to interface with a ChromeCast. """

    def __init__(self, host):
        self.logger = logging.getLogger(__name__)
        self.host = host

        self.logger.info("Querying device status")
        self.device = get_device_status(host)

        if not self.device:
            raise ConnectionError("Could not connect to {}".format(host))

        self.app = self.websocket_client = None

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
        """ Queries the Chromecast for the current status. """
        self.logger.info("Refreshing app status")

        self.app = app = get_app_status(self.host)

        if app:
            if self.app.service_protocols:
                try:
                    self.websocket_client = create_websocket_client(app)

                except ConnectionError:
                    self.websocket_client = None

            # The ramp service does not always immediately show up
            # Check if app is known to be RAMP controllable, then plan refresh
            elif app.app_id in RAMP_ENABLED:

                self._delayed_refresh()

        else:
            self.websocket_client = None

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
        threading.Timer(5, self.refresh).start()

    def __str__(self):
        return "PyChromecast({}, {}, {}, {}, api={}.{})".format(
            self.host, self.device.friendly_name, self.device.model_name,
            self.device.manufacturer, self.device.api_version[0],
            self.device.api_version[1])
