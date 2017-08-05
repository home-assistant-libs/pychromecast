"""
Controller to interface with the DashCast app namespace.
"""
from ..config import APP_DASHCAST
from . import BaseController


TYPE_LOAD = "load"

APP_NAMESPACE = "urn:x-cast:com.madmod.dashcast"


class DashCastController(BaseController):
    """ Controller to interact with DashCast app namespace. """

    def __init__(self,
                 appNamespace=APP_NAMESPACE,
                 appId=APP_DASHCAST):
        super(DashCastController, self).__init__(
            appNamespace, appId)

    def load_url(self, url, force=False, reload_seconds=0):
        """
        Starts loading a URL with an optional reload time
        in seconds.

        Setting force to True may load pages which block
        iframe embedding, but will cause calls to load_url()
        to fail until launch() is called manually.
        """
        def callback():
            """Loads requested URL after app launched."""
            reload = reload_seconds not in (0, None)
            reload_time = reload_seconds * 1000
            msg = {
                "url": url,
                "force": force,
                "reload": reload,
                "reload_time": reload_time
            }

            self.send_message(msg, inc_session_id=True)

        self.launch(callback_function=callback)
