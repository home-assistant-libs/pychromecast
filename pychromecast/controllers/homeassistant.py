"""
Controller to interface with Home Assistant
"""
from ..config import APP_HOME_ASSISTANT
from . import BaseController


APP_NAMESPACE = "urn:x-cast:com.nabucasa.hast"


class HomeAssistantController(BaseController):
    """ Controller to interact with Home Assistant. """

    # pylint: disable=useless-super-delegation
    # The pylint rule useless-super-delegation doesn't realize
    # we are setting default values here.
    def __init__(self,
                 app_namespace=APP_NAMESPACE,
                 app_id=APP_HOME_ASSISTANT):
        super().__init__(app_namespace, app_id)
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

    def show_lovelace(self, config, callback_function=None):
        """Show a Lovelace UI."""
        def launch_callback():
            """Loads requested URL after app launched."""
            msg = {
                "type": "show_lovelace",
                "config": config
            }

            self.send_message(msg, inc_session_id=True,
                              callback_function=callback_function)

        self.launch(callback_function=launch_callback)
