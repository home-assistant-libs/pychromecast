"""
Controller to interface with the DashCast app namespace.
"""
from ..config import APP_DASHCAST
from . import BaseController


APP_NAMESPACE = "urn:x-cast:com.madmod.dashcast"


class DashCastController(BaseController):
    """ Controller to interact with DashCast app namespace. """

    # pylint: disable=useless-super-delegation
    # The pylint rule useless-super-delegation doesn't realize
    # we are setting default values here.
    def __init__(self,
                 appNamespace=APP_NAMESPACE,
                 appId=APP_DASHCAST):
        super(DashCastController, self).__init__(
            appNamespace, appId)
    # pylint: enable=useless-super-delegation

    def receive_message(self, message, data):
        """
        Called when a load complete message is received.

        This is currently un-used by this controller. It is implemented
        so that we don't get "Message unhandled" warnings. In the future
        it might be used to update a public status object like the media
        controller does.
        """
        # Indicate that the message was successfully handled.
        return True

    def load_url(self, url, force=False, reload_seconds=0,
                 callback_function=None):
        """
        Starts loading a URL with an optional reload time
        in seconds.

        Setting force to True may load pages which block
        iframe embedding, but will prevent reload from
        working and will cause calls to load_url()
        to reload the app.
        """
        def launch_callback():
            """Loads requested URL after app launched."""
            should_reload = not force and reload_seconds not in (0, None)
            reload_milliseconds = (0 if not should_reload
                                   else reload_seconds * 1000)
            msg = {
                "url": url,
                "force": force,
                "reload": should_reload,
                "reload_time": reload_milliseconds
            }

            self.send_message(msg, inc_session_id=True,
                              callback_function=callback_function)

        self.launch(callback_function=launch_callback)
