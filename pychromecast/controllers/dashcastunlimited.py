"""
Controller to interface with the DashCast Unlimited app namespace. This fork of DashCast activates the disableIdleTimeout parameter which allows to keep the cast running unlimited time. Uses a new app id and namespace for future updates.
"""
from ..config import APP_DASHCAST_UNLIMITED
from . import BaseController


APP_NAMESPACE = "urn:x-cast:com.raulgbcr.dashcast-unlimited"


class DashCastUnlimitedController(BaseController):
    """Controller to interact with DashCast Unlimited app namespace."""

    def __init__(self, appNamespace=APP_NAMESPACE, appId=APP_DASHCAST_UNLIMITED):
        super().__init__(appNamespace, appId)

    def receive_message(self, _message, _data: dict):
        """
        Called when a load complete message is received.

        This is currently un-used by this controller. It is implemented
        so that we don't get "Message unhandled" warnings. In the future
        it might be used to update a public status object like the media
        controller does.
        """
        # Indicate that the message was successfully handled.
        return True

    def load_url(self, url, force=False, reload_seconds=0, callback_function=None):
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
            reload_milliseconds = 0 if not should_reload else reload_seconds * 1000
            msg = {
                "url": url,
                "force": force,
                "reload": should_reload,
                "reload_time": reload_milliseconds,
            }

            self.send_message(
                msg, inc_session_id=True, callback_function=callback_function
            )

        self.launch(callback_function=launch_callback)