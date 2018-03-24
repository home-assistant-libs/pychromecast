import logging
import os
import requests
import spotipy
import time

from pychromecast.controllers import BaseController
from ..config import APP_SPOTIFY

logging.basicConfig(level=logging.DEBUG)

APP_NAMESPACE = "urn:x-cast:com.spotify.chromecast.secure.v1"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/63.0.3239.132 Safari/537.36"

TYPE_STATUS = "setCredentials"


class SpotifyController(BaseController):
    def __init__(self, friendly_name, username=None, password=None):
        super(SpotifyController, self).__init__(
              APP_NAMESPACE, APP_SPOTIFY)

        self.logger = logging.getLogger(__name__)
        self.username = username
        self.password = password
        self.cast_name = friendly_name
        self.session_started = False
        self.token = None
        self.expiration_date = None
        self.client = None
        self.device_id = None

    def receive_message(self, message, data):
        self.logger.debug("Cast message: {}".format(data))

        return True

    def _get_csrf(self, session, cookies):
        headers = {'user-agent': USER_AGENT}

        response = session.get("https://accounts.spotify.com/login",
                               headers=headers, cookies=cookies)
        response.raise_for_status()

        return response.cookies['csrf_token']

    def _login(self, session, cookies, username, password, csrf_token):
        headers = {'user-agent': USER_AGENT}

        data = {"remember": False, "username": username, "password": password,
                "csrf_token": csrf_token}

        response = session.post("https://accounts.spotify.com/api/login",
                                data=data, cookies=cookies, headers=headers)

        response.raise_for_status()

    def _get_access_token(self, session, cookies):
        headers = {'user-agent': USER_AGENT}

        response = session.get("https://open.spotify.com/browse",
                               headers=headers, cookies=cookies)
        response.raise_for_status()

        self.token = response.cookies['wp_access_token']

        expiration = response.cookies['wp_expiration']
        self.expiration_date = int(expiration)//1000

    def start_session(self):
        # arbitrary value and can be static
        cookies = {"__bon": "MHwwfC01ODc4MjExMzJ8LTI0Njg4NDg3NTQ0fDF8MXwxfDE="}

        if self.username is None:
            self.username = os.getenv("SPOTIFY_USERNAME")

        if self.password is None:
            self.password = os.getenv("SPOTIFY_PASS")

        if self.username is None or self.password is None:
            raise("No username or password")

        session = requests.Session()
        token = self. _get_csrf(session, cookies)

        self._login(session, cookies, self.username, self.password, token)
        self._get_access_token(session, cookies)

        self.session_started = True

        return self.token

    def launch_app(self):

        def callback():
            self.send_message({"type": TYPE_STATUS, "credentials": self.token})

        curr_time = time.time()

        if self.session_started and curr_time < self.expiration_date:
            self.logger.debug("Using same token: {}".format(self.token))
            self.launch(callback_function=callback)
        else:
            self.logger.debug("Creating new token")
            self.start_session()
            self.logger.debug("Token is: {}".format(self.token))
            self.launch(callback_function=callback)

        # TODO: Remove sleep and find another way to wait for app to go up completely
        time.sleep(5)
        self.client = spotipy.Spotify(auth=self.token)

        self.device_id = self.get_spotify_device_id()

    def get_spotify_device_id(self):

        devices_available = self.client.devices();

        for device in devices_available['devices']:
            self.logger.debug(device)
            if device['name'] == self.cast_name:
                return device['id']
        return None

    def play_song(self, uri):
        if self.device_id is None:
            raise("No device id. Try launching app again")
        else:
            self.client.start_playback(device_id=self.device_id, uris=[uri])

    def play_songs(self, uris):

        self.client.start_playback(device_id=self.device_id, uris=uris)

    def play_context(self, context_uri, offset=None):

        self.client.start_playback(device_id=self.device_id,context_uri=context_uri, offset=offset)



