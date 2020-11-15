"""
Controller to interface with Spotify.
"""
import logging
import threading
import time
import json

from . import BaseController
from ..config import APP_SPOTIFY
from ..error import LaunchError

APP_NAMESPACE = "urn:x-cast:com.spotify.chromecast.secure.v1"
TYPE_GET_INFO = "getInfo"
TYPE_GET_INFO_RESPONSE = "getInfoResponse"
TYPE_SET_CREDENTIALS = "setCredentials"
TYPE_SET_CREDENTIALS_ERROR = "setCredentialsError"
TYPE_SET_CREDENTIALS_RESPONSE = "setCredentialsResponse"

LAUNCH_TIMEOUT_MSG = "Timeout when waiting for status response from Spotify app"


# pylint: disable=too-many-instance-attributes
class SpotifyController(BaseController):
    """ Controller to interact with Spotify namespace. """

    # pylint: disable=useless-super-delegation
    # The pylint rule useless-super-delegation doesn't realize
    # we are setting default values here.
    def __init__(self, access_token, expires):
        super(SpotifyController, self).__init__(APP_NAMESPACE, APP_SPOTIFY)
        if access_token is None or expires is None:
            raise ValueError("access_token and expires cannot be empty")

        self.logger = logging.getLogger(__name__)
        self.session_started = False
        self.access_token = access_token
        self.expires = expires
        self.is_launched = False
        self.device = None
        self.credential_error = False
        self.waiting = threading.Event()

    # pylint: enable=useless-super-delegation

    # pylint: disable=unused-argument,no-self-use
    def receive_message(self, message, data: dict):
        """
        Handle the auth flow and active player selection.

        Called when a message is received.
        """
        if data["type"] == TYPE_SET_CREDENTIALS_RESPONSE:
            self.send_message({"type": TYPE_GET_INFO, "payload": {}})
        if data["type"] == TYPE_SET_CREDENTIALS_ERROR:
            self.device = None
            self.credential_error = True
            self.waiting.set()
        if data["type"] == TYPE_GET_INFO_RESPONSE:
            self.device = data["payload"]["deviceID"]
            self.is_launched = True
            self.waiting.set()
        return True

    def launch_app(self, timeout=10):
        """
        Launch Spotify application.

        Will raise a LaunchError exception if there is no response from the
        Spotify app within timeout seconds.
        """

        def callback():
            """Callback function"""
            self.send_message(
                {
                    "type": TYPE_SET_CREDENTIALS,
                    "credentials": self.access_token,
                    "expiresIn": self.expires,
                }
            )

        self.device = None
        self.credential_error = False
        self.waiting.clear()
        self.launch(callback_function=callback)

        # Need to wait for Spotify to be launched on Chromecast completely
        self.waiting.wait(timeout)

        if not self.is_launched:
            raise LaunchError(LAUNCH_TIMEOUT_MSG)

    @classmethod
    def from_cookie(cls, sp_dc, sp_key):
        """ Generate a SpotifyController from given cookie values from spotify web player """
        try:
            # pylint: disable=import-outside-toplevel
            import spotify_token as st
        except ImportError:
            raise ImportError(
                """
                You need to install the spotipy and spotify-token dependencies.

                This can be done by running the following:
                pip install spotify-token
                pip install git+https://github.com/plamere/spotipy.git
                """
            )
        data = st.start_session(sp_dc, sp_key)
        access_token = data[0]
        expires = data[1] - int(time.time())
        return cls(access_token, expires)

    # pylint: disable=too-many-locals
    def quick_play(self, media_id=None, **kwargs):
        """ Quick Play """
        # pylint: disable=import-outside-toplevel
        import spotipy

        # Create a spotify client
        client = spotipy.Spotify(auth=self.access_token)

        try:
            self.launch_app(timeout=0)
        except LaunchError as error:
            if str(error) != LAUNCH_TIMEOUT_MSG:
                raise

        counter = 0
        while counter < 10:
            if self.is_launched:
                break
            time.sleep(1)
            counter += 1

        if not self.is_launched:
            raise LaunchError(LAUNCH_TIMEOUT_MSG)

        # Query spotify for active devices
        devices_available = client.devices()

        # Match active spotify devices with the spotify controller's device id
        spotify_device_id = None
        for device in devices_available["devices"]:
            if device["id"] == self.device:
                spotify_device_id = device["id"]
                break

        if not spotify_device_id:
            logging.error('No device with id "%s" known by Spotify', self.device)
            logging.error("Known devices: %s", devices_available["devices"])
            return

        # Parse media_id (allow sending JSON formatted list)
        try:
            json_media = json.loads(media_id)
            if not isinstance(json_media, list):
                json_media = [json_media]
        except json.JSONDecodeError:
            logging.debug("Not a JSON formatted string: %s", media_id)
            json_media = [media_id]

        # Start playback
        if json_media[0].find("track") > 0:
            client.start_playback(device_id=spotify_device_id, uris=json_media)
        else:
            client.start_playback(
                device_id=spotify_device_id, context_uri=json_media[0]
            )
