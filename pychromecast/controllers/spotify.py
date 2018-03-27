"""
Controller to interface with the DashCast app namespace.
"""
import logging
import os
import time
import requests
import spotipy

from pychromecast.controllers import BaseController
from ..config import APP_SPOTIFY

logging.basicConfig(level=logging.DEBUG)

APP_NAMESPACE = "urn:x-cast:com.spotify.chromecast.secure.v1"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_2) \
AppleWebKit/537.36 (KHTML, like Gecko) Chrome/63.0.3239.132 Safari/537.36"

TYPE_STATUS = "setCredentials"

# pylint: disable=too-many-instance-attributes
class SpotifyController(BaseController):
    """ Controller to interact with Spotify namespace. """

    # pylint: disable=useless-super-delegation
    # The pylint rule useless-super-delegation doesn't realize
    # we are setting default values here.
    def __init__(self, friendly_name, username=None, password=None):
        super(SpotifyController, self).__init__(APP_NAMESPACE, APP_SPOTIFY)

        self.logger = logging.getLogger(__name__)
        self.username = username
        self.password = password
        self.cast_name = friendly_name
        self.session_started = False
        self.token = None
        self.expiration_date = None
        self.client = None
        self.device_id = None
    # pylint: enable=useless-super-delegation

    # pylint: disable=unused-argument,no-self-use
    def receive_message(self, message, data):
        """ Currently not doing anything with received messages. """
        return True

    def _get_csrf(self, session, cookies):
        """ Get CSRF token for Spotify login. """
        headers = {'user-agent': USER_AGENT}

        response = session.get("https://accounts.spotify.com/login",
                               headers=headers, cookies=cookies)
        response.raise_for_status()

        return response.cookies['csrf_token']

    # pylint: disable=too-many-arguments
    def _login(self, session, cookies, username, password, csrf_token):
        """ Logs in with CSRF token and cookie within session. """
        headers = {'user-agent': USER_AGENT}

        data = {"remember": False, "username": username, "password": password,
                "csrf_token": csrf_token}

        response = session.post("https://accounts.spotify.com/api/login",
                                data=data, cookies=cookies, headers=headers)

        response.raise_for_status()

    def _get_access_token(self, session, cookies):
        """ Gets access token after login has been successful. """
        headers = {'user-agent': USER_AGENT}

        response = session.get("https://open.spotify.com/browse",
                               headers=headers, cookies=cookies)
        response.raise_for_status()

        self.token = response.cookies['wp_access_token']

        expiration = response.cookies['wp_expiration']
        self.expiration_date = int(expiration)//1000

    # Access token provided by spotipy does not have enough permissions to start
    # Spotify on Chromecast
    def start_session(self):
        """ Starts session to get access token. """

        # arbitrary value and can be static
        cookies = {"__bon": "MHwwfC01ODc4MjExMzJ8LTI0Njg4NDg3NTQ0fDF8MXwxfDE="}

        if self.username is None:
            self.username = os.getenv("SPOTIFY_USERNAME")

        if self.password is None:
            self.password = os.getenv("SPOTIFY_PASS")

        if self.username is None or self.password is None:
            raise Exception("No username or password")

        session = requests.Session()
        token = self. _get_csrf(session, cookies)

        self._login(session, cookies, self.username, self.password, token)
        self._get_access_token(session, cookies)

        self.session_started = True

        return self.token

    def launch_app(self):
        """ Launch main application """

        def callback():
            """Callback function"""
            self.send_message({"type": TYPE_STATUS, "credentials": self.token})

        curr_time = time.time()

        if self.session_started and curr_time < self.expiration_date:
            self.logger.debug("Using same token: %s", self.token)
            self.launch(callback_function=callback)
        else:
            self.logger.debug("Creating new token")
            self.start_session()
            self.logger.debug("Token is: %s", self.token)
            self.launch(callback_function=callback)

        # Need to wait for Spotify to be launched on Chromecast completely
        time.sleep(5)
        self.client = spotipy.Spotify(auth=self.token)

        self.device_id = self.get_spotify_device_id()

    def get_spotify_device_id(self):
        """
        Gets device id from Spotify. This should be the same as the name of
        the Chromecast.
        """
        devices_available = self.client.devices()

        for device in devices_available['devices']:
            self.logger.debug(device)
            if device['name'] == self.cast_name:
                return device['id']
        return None

    def play_song(self, uri):
        """ Play a single song with it's Spotify URI. """
        if self.device_id is None:
            raise Exception("No device id. Try launching app again")
        else:
            self.client.start_playback(device_id=self.device_id, uris=[uri])

    def play_songs(self, uris):
        """ Play several songs with a list of uris. """
        if self.device_id is None:
            raise Exception("No device id. Try launching app again")
        else:
            self.client.start_playback(device_id=self.device_id, uris=uris)

    def play_context(self, context_uri, offset=None):
        """ Play a Spotify context.
            Valid contexts are albums, artists and playlists.
        """
        if self.device_id is None:
            raise Exception("No device id. Try launching app again")
        else:
            self.client.start_playback(device_id=self.device_id,
                                       context_uri=context_uri, offset=offset)
