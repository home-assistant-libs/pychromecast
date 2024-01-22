"""
Controller to interface with Home Assistant
"""
from functools import partial
import threading

from ..config import APP_HOMEASSISTANT_LOVELACE
from ..error import PyChromecastError
from ..response_handler import chain_on_success
from . import BaseController


APP_NAMESPACE = "urn:x-cast:com.nabucasa.hast"
DEFAULT_HASS_CONNECT_TIMEOUT = 30

# Error codes sent in receiver_error messages
ERR_CONNECTION_FAILED = 1
ERR_AUTHENTICATION_FAILED = 2
ERR_CONNECTION_LOST = 3
ERR_HASS_URL_MISSING = 4
ERR_NO_HTTPS = 5
ERR_WRONG_INSTANCE = 20
ERR_NOT_CONNECTED = 21
ERR_FETCH_CONFIG_FAILED = 22


class HomeAssistantController(BaseController):
    """Controller to interact with Home Assistant."""

    def __init__(
        self,
        *,
        hass_url,
        hass_uuid,
        client_id,
        refresh_token,
        unregister,
        app_namespace=APP_NAMESPACE,
        app_id=APP_HOMEASSISTANT_LOVELACE,
        hass_connect_timeout=DEFAULT_HASS_CONNECT_TIMEOUT,
    ):
        super().__init__(app_namespace, app_id)
        self.hass_url = hass_url
        self.hass_uuid = hass_uuid
        self.client_id = client_id
        self.refresh_token = refresh_token
        self.unregister = unregister
        self.hass_connect_timeout = hass_connect_timeout
        # {
        #   connected: boolean;
        #   showDemo: boolean;
        #   hassUrl?: string;
        #   lovelacePath?: string | number | null;
        #   urlPath?: string | null;
        # }
        self.status = None
        self._hass_connecting_event = threading.Event()
        self._hass_connecting_event.set()
        self._on_connect = []

    @property
    def hass_connected(self):
        """Return if connected to Home Assistant."""
        return (
            self.status is not None
            and self.status["connected"]
            and self.status["hassUrl"] == self.hass_url
            and self.status["hassUUID"] == self.hass_uuid
        )

    def channel_connected(self):
        """Called when a channel has been openend that supports the
        namespace of this controller."""
        self.get_status()

    def channel_disconnected(self):
        """Called when a channel is disconnected."""
        self.status = None
        self._hass_connecting_event.set()

    def receive_message(self, _message, data: dict):
        """Called when a message is received."""
        if data.get("type") == "receiver_status":
            if data["hassUrl"] != self.hass_url or data["hassUUID"] != self.hass_uuid:
                self.logger.info("Received status for another instance")
                self.unregister()
                return True

            was_connected = self.hass_connected
            self.status = data

            if was_connected or not self.hass_connected:
                return True

            # We just got connected, call the callbacks.
            self._hass_connecting_event.set()
            self._call_on_connect_callbacks(True)
            return True

        if data.get("type") == "receiver_error":
            if data.get("error_code") == ERR_WRONG_INSTANCE:
                self.logger.info("Received ERR_WRONG_INSTANCE")
                self.unregister()
            return True

        return False

    def _call_on_connect_callbacks(self, msg_sent: bool) -> None:
        """Call on connect callbacks."""
        while self._on_connect:
            self._on_connect.pop()(msg_sent, None)

    def _connect_hass(self, callback_function):
        """Connect to Home Assistant and call the provided callback."""
        self._on_connect.append(callback_function)

        if not self._hass_connecting_event.is_set():
            return

        self._hass_connecting_event.clear()
        try:
            self.send_message(
                {
                    "type": "connect",
                    "refreshToken": self.refresh_token,
                    "clientId": self.client_id,
                    "hassUrl": self.hass_url,
                    "hassUUID": self.hass_uuid,
                }
            )
        except Exception:  # pylint: disable=broad-except
            self._hass_connecting_event.set()
            self._call_on_connect_callbacks(False)
            raise

        self._hass_connecting_event.wait(self.hass_connect_timeout)
        try:
            if not self._hass_connecting_event.is_set():
                self.logger.warning("_connect_hass failed for %s", self.hass_url)
                raise PyChromecastError()  # pylint: disable=broad-exception-raised
        finally:
            self._hass_connecting_event.set()
            self._call_on_connect_callbacks(False)

    def show_demo(self):
        """Show the demo."""
        self.send_message({"type": "show_demo"})

    def get_status(self, callback_function=None):
        """Get status of Home Assistant Cast."""
        self._send_connected_message(
            {
                "type": "get_status",
                "hassUrl": self.hass_url,
                "hassUUID": self.hass_uuid,
            },
            callback_function=callback_function,
        )

    def show_lovelace_view(self, view_path, url_path=None, callback_function=None):
        """Show a Lovelace UI."""
        self._send_connected_message(
            {
                "type": "show_lovelace_view",
                "hassUrl": self.hass_url,
                "hassUUID": self.hass_uuid,
                "viewPath": view_path,
                "urlPath": url_path,
            },
            callback_function=callback_function,
        )

    def _send_connected_message(self, data, callback_function):
        """Send a message to a connected Home Assistant Cast"""
        if self.hass_connected:
            self.send_message_nocheck(data, callback_function=callback_function)
            return

        self._connect_hass(
            chain_on_success(
                partial(self.send_message_nocheck, data), callback_function
            )
        )
