"""
Provides controllers to handle specific namespaces in Chromecast communication.
"""
from __future__ import annotations

import abc
import logging
from typing import TYPE_CHECKING

from ..error import UnsupportedNamespace, ControllerNotRegistered

if TYPE_CHECKING:
    from ..socket_client import SocketClient


class BaseController(abc.ABC):
    """ABC for namespace controllers."""

    def __init__(
        self,
        namespace,
        supporting_app_id=None,
        target_platform=False,
        app_must_match=False,
    ):
        """
        Initialize the controller.

        namespace:         the namespace this controller will act on
        supporting_app_id: app to be launched if app is running with
                           unsupported namespace.
        target_platform:   set to True if you target the platform instead of
                           current app.
        app_must_match:    set to True if the app should be launched even if the
                           namespace is supported by another app.
        """
        self.app_must_match = app_must_match
        self.namespace = namespace
        self.supporting_app_id = supporting_app_id
        self.target_platform = target_platform

        self._socket_client: SocketClient | None = None
        self._message_func = None

        self.logger = logging.getLogger(__name__)

    @property
    def is_active(self):
        """True if the controller is connected to a socket client and the
        Chromecast is running an app that supports this controller."""
        return (
            self._socket_client is not None
            and self.namespace in self._socket_client.app_namespaces
        )

    def launch(self, callback_function=None, force_launch=False):
        """If set, launches app related to the controller."""
        self._check_registered()

        self._socket_client.receiver_controller.launch_app(
            self.supporting_app_id,
            force_launch=force_launch,
            callback_function=callback_function,
        )

    def registered(self, socket_client):
        """Called when a controller is registered."""
        self._socket_client = socket_client

        if self.target_platform:
            self._message_func = self._socket_client.send_platform_message
        else:
            self._message_func = self._socket_client.send_app_message

    def unregistered(self):
        """Called when a controller is unregistered."""
        self._message_func = None

    def channel_connected(self):
        """Called when a channel has been openend that supports the
        namespace of this controller."""

    def channel_disconnected(self):
        """Called when a channel is disconnected."""

    def send_message(
        self,
        data,
        inc_session_id=False,
        callback_function=None,
        no_add_request_id=False,
    ):
        """
        Send a message on this namespace to the Chromecast. Ensures app is loaded.

        Will raise a NotConnected exception if not connected.
        """
        self._check_registered()

        receiver_ctrl = self._socket_client.receiver_controller

        if not self.target_platform and (
            self.namespace not in self._socket_client.app_namespaces
            or (self.app_must_match and receiver_ctrl.app_id != self.supporting_app_id)
        ):
            if self.supporting_app_id is not None:
                self.launch(
                    callback_function=lambda: self.send_message_nocheck(
                        data,
                        inc_session_id,
                        callback_function,
                        no_add_request_id=no_add_request_id,
                    )
                )
                return

            raise UnsupportedNamespace(
                f"Namespace {self.namespace} is not supported by running application."
            )

        self.send_message_nocheck(
            data, inc_session_id, callback_function, no_add_request_id=no_add_request_id
        )

    def send_message_nocheck(
        self,
        data,
        inc_session_id=False,
        callback_function=None,
        no_add_request_id=False,
    ):
        """Send a message."""
        self._message_func(
            self.namespace,
            data,
            inc_session_id,
            callback_function,
            no_add_request_id=no_add_request_id,
        )

    def receive_message(self, _message, _data: dict):
        """
        Called when a message is received that matches the namespace.
        Returns boolean indicating if message was handled.
        data is message.payload_utf8 interpreted as a JSON dict.
        """
        return False

    def tear_down(self):
        """Called when we are shutting down."""
        self._socket_client = None
        self._message_func = None

    def _check_registered(self):
        """Helper method to see if we are registered with a Cast object."""
        if self._socket_client is None:
            raise ControllerNotRegistered(
                (
                    "Trying to use the controller without it being registered "
                    "with a Cast object."
                )
            )
