"""
Controller to interface with the DashCast app namespace.
"""
import logging
import time

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

    def launch_app(self):
        """ Launch main application """

        def callback():
            """Callback function"""
            self.send_message({"type": TYPE_STATUS,
                               "credentials": self.access_token})

        self.launch(callback_function=callback)

        # Need to wait for Spotify to be launched on Chromecast completely
        while not self.is_launched:
            time.sleep(1)
