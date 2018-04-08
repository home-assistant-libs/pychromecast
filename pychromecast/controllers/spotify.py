"""
Controller to interface with the DashCast app namespace.
"""
import logging
import time
import spotipy
import spotify_token

from . import BaseController
from ..config import APP_SPOTIFY

logging.basicConfig(level=logging.DEBUG)

APP_NAMESPACE = "urn:x-cast:com.spotify.chromecast.secure.v1"
TYPE_STATUS = "setCredentials"
TYPE_RESPONSE_STATUS = 'setCredentialsResponse'


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
        self.is_launched = False
    # pylint: enable=useless-super-delegation

    # pylint: disable=unused-argument,no-self-use
    def receive_message(self, message, data):
        """ Currently not doing anything with received messages. """
        if data['type'] == TYPE_RESPONSE_STATUS:
            self.is_launched = True
        return True

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

            data = spotify_token.start_session(self.username, self.password)
            self.session_started = True
            self.token = data[0]
            self.expiration_date = data[1]

            self.logger.debug("Token is: %s", self.token)
            self.launch(callback_function=callback)

        # Need to wait for Spotify to be launched on Chromecast completely
        while not self.is_launched:
            time.sleep(1)

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
            if (device['name'] == self.cast_name and
                    device['type'] == 'CastVideo'):
                return device['id']
        return None

    def play_song(self, uri):
        """ Play a single song with it's Spotify URI. """
        if self.device_id is None:
            raise Exception("No device id. Try launching app again")
        self.client.start_playback(device_id=self.device_id, uris=[uri])

    def play_songs(self, uris):
        """ Play several songs with a list of uris. """
        if self.device_id is None:
            raise Exception("No device id. Try launching app again")
        self.client.start_playback(device_id=self.device_id, uris=uris)

    def play_context(self, context_uri, offset=None):
        """ Play a Spotify context.
            Valid contexts are albums, artists and playlists.
        """
        if self.device_id is None:
            raise Exception("No device id. Try launching app again")
        self.client.start_playback(device_id=self.device_id,
                                   context_uri=context_uri, offset=offset)
