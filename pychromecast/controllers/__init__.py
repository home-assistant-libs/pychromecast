"""
Provides controllers to handle specific namespaces in Chromecast communication.
"""

from __future__ import annotations

import abc
from functools import partial
import logging
from typing import TYPE_CHECKING, Any, Protocol

from ..error import UnsupportedNamespace, ControllerNotRegistered
from ..generated.cast_channel_pb2 import (  # pylint: disable=no-name-in-module
    CastMessage,
)
from ..response_handler import CallbackType, chain_on_success

if TYPE_CHECKING:
    from ..socket_client import SocketClient


class SendMessageFunc(Protocol):
    """Protocol for SocketClient's send message functions."""

    def __call__(
        self,
        namespace: str,
        message: Any,
        *,
        inc_session_id: bool = False,
        callback_function: CallbackType | None = None,
        no_add_request_id: bool = False,
    ) -> None: ...


class BaseController(abc.ABC):
    """ABC for namespace controllers."""

    def __init__(
        self,
        namespace: str,
        supporting_app_id: str | None = None,
        target_platform: bool = False,
        app_must_match: bool = False,
    ) -> None:
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
        self._message_func: SendMessageFunc | None = None

        self.logger = logging.getLogger(__name__)

    @property
    def is_active(self) -> bool:
        """True if the controller is connected to a socket client and the
        Chromecast is running an app that supports this controller."""
        return (
            self._socket_client is not None
            and self.namespace in self._socket_client.app_namespaces
        )

    def launch(
        self,
        *,
        callback_function: CallbackType | None = None,
        force_launch: bool = False,
    ) -> None:
        """If set, launches app related to the controller."""
        if self.supporting_app_id is None:
            self.logger.debug(
                "%s: Can't launch app with no supporting app_id",
                self.__class__.__name__,
            )
            if callback_function:
                callback_function(False, None)
            return

        if self._socket_client is None:
            if callback_function:
                callback_function(False, None)
            raise ControllerNotRegistered

        self._socket_client.receiver_controller.launch_app(
            self.supporting_app_id,
            force_launch=force_launch,
            callback_function=callback_function,
        )

    def registered(self, socket_client: SocketClient) -> None:
        """Called when a controller is registered."""
        self._socket_client = socket_client

        if self.target_platform:
            self._message_func = self._socket_client.send_platform_message
        else:
            self._message_func = self._socket_client.send_app_message

    def unregistered(self) -> None:
        """Called when a controller is unregistered."""
        self._message_func = None

    def channel_connected(self) -> None:
        """Called when a channel has been openend that supports the
        namespace of this controller."""

    def channel_disconnected(self) -> None:
        """Called when a channel is disconnected."""

    def send_message(
        self,
        data: Any,
        *,
        inc_session_id: bool = False,
        callback_function: CallbackType | None = None,
        no_add_request_id: bool = False,
    ) -> None:
        """
        Send a message on this namespace to the Chromecast. Ensures app is loaded.

        Will raise a NotConnected exception if not connected.
        """
        if self._socket_client is None:
            if callback_function:
                callback_function(False, None)
            raise ControllerNotRegistered

        receiver_ctrl = self._socket_client.receiver_controller

        if not self.target_platform and (
            self.namespace not in self._socket_client.app_namespaces
            or (self.app_must_match and receiver_ctrl.app_id != self.supporting_app_id)
        ):
            if self.supporting_app_id is not None:
                self.launch(
                    callback_function=chain_on_success(
                        partial(
                            self.send_message_nocheck,
                            data,
                            inc_session_id=inc_session_id,
                            no_add_request_id=no_add_request_id,
                        ),
                        callback_function,
                    )
                )
                return

            if callback_function:
                callback_function(False, None)
            raise UnsupportedNamespace(
                f"Namespace {self.namespace} is not supported by running application."
            )

        self.send_message_nocheck(
            data,
            inc_session_id=inc_session_id,
            callback_function=callback_function,
            no_add_request_id=no_add_request_id,
        )

    def send_message_nocheck(
        self,
        data: Any,
        *,
        inc_session_id: bool = False,
        callback_function: CallbackType | None = None,
        no_add_request_id: bool = False,
    ) -> None:
        """Send a message."""
        if TYPE_CHECKING:
            assert self._message_func

        self._message_func(
            self.namespace,
            data,
            inc_session_id=inc_session_id,
            callback_function=callback_function,
            no_add_request_id=no_add_request_id,
        )

    def receive_message(self, _message: CastMessage, _data: dict) -> bool:
        """
        Called when a message is received that matches the namespace.
        Returns boolean indicating if message was handled.
        data is message.payload_utf8 interpreted as a JSON dict.
        """
        return False

    def tear_down(self) -> None:
        """Called when we are shutting down."""
        self._socket_client = None
        self._message_func = None


class QuickPlayController(BaseController, abc.ABC):
    """ABC for controller which supports quick play."""

    @abc.abstractmethod
    def quick_play(self, *, media_id: str, timeout: float, **kwargs: Any) -> None:
        """Quick Play support for a controller."""
