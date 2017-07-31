"""
Controller to interface with the chromecast-dashboard app.
"""
import time

from . import BaseController


TYPE_LOAD = "load"

APP_NAMESPACE = "urn:x-cast:com.boombatower.chromecast-dashboard"
APP_ID = "F7FD2183"


class ChromecastDashboardController(BaseController):
    """ Controller to interact with chromecast-dashboard namespace. """

    def __init__(self):
        super(ChromecastDashboardController, self).__init__(APP_NAMESPACE, APP_ID)

    def load_url(self, url, refresh_seconds=0):
        """ Starts loading a URL with an optional refresh time in seconds. """
        def callback():
            """Loads requested URL after app launched."""
            msg = {
                "type": TYPE_LOAD,
                "url": url,
                "refresh": refresh_seconds
            }

            self.send_message(msg, inc_session_id=True)

        # TODO: Add timeout.
        # TODO: Find a better way to do this.
        if self._socket_client.blocking:
            self.launch()
            while not self.is_active:
                time.sleep(0.1)
            callback()
        else:
            self.launch(callback)

