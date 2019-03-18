"""
Controller to interface with Spotify.
"""
import logging
import time

from . import BaseController
from ..config import APP_SPOTIFY
from ..error import LaunchError

APP_NAMESPACE = "urn:x-cast:com.spotify.chromecast.secure.v1"
TYPE_STATUS = "setCredentials"
TYPE_RESPONSE_STATUS = 'setCredentialsResponse'


# pylint: disable=too-many-instance-attributes
class SpotifyController(BaseController):
    """ Controller to interact with Spotify namespace. """

    # pylint: disable=useless-super-delegation
    # The pylint rule useless-super-delegation doesn't realize
    # we are setting default values here.
    def __init__(self, access_token):
        super(SpotifyController, self).__init__(APP_NAMESPACE, APP_SPOTIFY)

        self.logger = logging.getLogger(__name__)
        self.session_started = False
        self.access_token = access_token
        self.is_launched = False
    # pylint: enable=useless-super-delegation

    # pylint: disable=unused-argument,no-self-use
    def receive_message(self, message, data):
        """ Currently not doing anything with received messages. """
        if data['type'] == TYPE_RESPONSE_STATUS:
            self.is_launched = True
        return True

    def launch_app(self, timeout=10):
        """
        Launch Spotify application.

        Will raise a LaunchError exception if there is no response from the
        Spotify app within timeout seconds.
        """

        def callback():
            """Callback function"""
            self.send_message({"type": TYPE_STATUS,
                               "credentials": self.access_token,
                               "expiresIn": 3600})

        self.launch(callback_function=callback)

        # Need to wait for Spotify to be launched on Chromecast completely
        while not self.is_launched and timeout:
            time.sleep(1)
            timeout -= 1

        if not self.is_launched:
            raise LaunchError(
                "Timeout when waiting for status response from Spotify app")
