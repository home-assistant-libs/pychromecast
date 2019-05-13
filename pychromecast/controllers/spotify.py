"""
Controller to interface with Spotify.
"""
import logging
import threading

from . import BaseController
from ..config import APP_SPOTIFY
from ..error import LaunchError

APP_NAMESPACE = "urn:x-cast:com.spotify.chromecast.secure.v1"
TYPE_GET_INFO = "getInfo"
TYPE_GET_INFO_RESPONSE = "getInfoResponse"
TYPE_SET_CREDENTIALS = "setCredentials"
TYPE_SET_CREDENTIALS_ERROR = 'setCredentialsError'
TYPE_SET_CREDENTIALS_RESPONSE = 'setCredentialsResponse'


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
    def receive_message(self, message, data):
        """ Handle the auth flow and active player selection """
        if data['type'] == TYPE_SET_CREDENTIALS_RESPONSE:
            self.send_message({'type': TYPE_GET_INFO, 'payload': {}})
        if data['type'] == TYPE_SET_CREDENTIALS_ERROR:
            self.device = None
            self.credential_error = True
            self.waiting.set()
        if data['type'] == TYPE_GET_INFO_RESPONSE:
            self.device = data['payload']['deviceID']
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
            self.send_message({"type": TYPE_SET_CREDENTIALS,
                               "credentials": self.access_token,
                               "expiresIn": self.expires})

        self.device = None
        self.credential_error = False
        self.waiting.clear()
        self.launch(callback_function=callback)

        # Need to wait for Spotify to be launched on Chromecast completely
        self.waiting.wait(timeout)

        if not self.is_launched:
            raise LaunchError(
                "Timeout when waiting for status response from Spotify app")
