"""
Controller to interface with Home Assistant
"""
from ..config import APP_HOME_ASSISTANT
from . import BaseController


APP_NAMESPACE = "urn:x-cast:com.nabucasa.hast"


class HomeAssistantController(BaseController):
    """Controller to interact with Home Assistant."""

    def __init__(
        self,
        hass_url,
        client_id,
        refresh_token,
        app_namespace=APP_NAMESPACE,
        app_id=APP_HOME_ASSISTANT,
    ):
        super().__init__(app_namespace, app_id)
        self.hass_url = hass_url
        self.client_id = client_id
        self.refresh_token = refresh_token
        # {
        #   connected: boolean;
        #   showDemo: boolean;
        #   hassUrl?: string;
        #   lovelacePath?: string | number | null;
        # }
        self.status = None
        self._on_connect = []

    @property
    def hass_connected(self):
        """Return if connected to Home Assistant."""
        return (
            self.status is not None
            and self.status["connected"]
            and self.status["hassUrl"] == self.hass_url
        )

    def channel_connected(self):
        """Called when a channel has been openend that supports the
        namespace of this controller."""
        self.get_status()

    def channel_disconnected(self):
        """Called when a channel is disconnected."""
        self.status = None

    def receive_message(self, _message, data: dict):
        """Called when a message is received."""
        if data.get("type") == "receiver_status":
            was_connected = self.hass_connected
            self.status = data

            if was_connected or not self.hass_connected:
                return True

            # We just got connected, call the callbacks.
            while self._on_connect:
                self._on_connect.pop()()

            return True

        return False

    def connect_hass(self, callback_function=None):
        """Connect to Home Assistant."""
        self._on_connect.append(callback_function)
        self.send_message(
            {
                "type": "connect",
                "refreshToken": self.refresh_token,
                "clientId": self.client_id,
                "hassUrl": self.hass_url,
            }
        )

    def show_demo(self):
        """Show the demo."""
        self.send_message({"type": "show_demo"})

    def get_status(self, callback_function=None):
        """Get status of Home Assistant Cast."""
        self.send_connected_message(
            {"type": "get_status"}, callback_function=callback_function
        )

    def show_lovelace_view(self, view_path, url_path=None, callback_function=None):
        """Show a Lovelace UI."""
        self.send_connected_message(
            {"type": "show_lovelace_view", "viewPath": view_path, "urlPath": url_path},
            callback_function=callback_function,
        )

    def send_connected_message(self, data, callback_function=None):
        """Send a message to a connected Home Assistant Cast"""
        if self.hass_connected:
            self.send_message_nocheck(data, callback_function=callback_function)
            return

        self.connect_hass(
            lambda: self.send_message_nocheck(data, callback_function=callback_function)
        )
