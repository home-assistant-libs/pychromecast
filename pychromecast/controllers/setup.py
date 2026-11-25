"""
Controller for the setup namespace of the platform receiver.
"""

from collections.abc import Callable
from http import HTTPStatus
import threading
from typing import TYPE_CHECKING, cast

from . import BaseController, CallbackType
from ..const import MESSAGE_TYPE, REQUEST_TIMEOUT
from ..dial import EurekaInfo

# pylint: disable-next=no-name-in-module
from ..generated.cast_channel_pb2 import CastMessage
from ..response_handler import WaitResponse
from ..socket_client import (
    CONNECTION_STATUS_CONNECTED,
    ConnectionStatus,
    ConnectionStatusListener,
)

if TYPE_CHECKING:
    from ..socket_client import SocketClient

NS_SETUP = "urn:x-cast:com.google.cast.setup"
TYPE_EUREKA_INFO = "eureka_info"

# The setup namespace matches replies on request_id, a request with a
# requestId gets no reply
SETUP_REQUEST_ID = "request_id"


class SetupController(BaseController, ConnectionStatusListener):
    """Controller to query the platform receiver's setup namespace.

    The setup namespace answers eureka_info with the same data as the
    eureka_info HTTP endpoint. The endpoints of groups don't answer.
    """

    def __init__(self) -> None:
        super().__init__(NS_SETUP, target_platform=True)
        self._lock = threading.Lock()
        self._request_id = 0
        self._callbacks: dict[int, CallbackType] = {}
        self._remove_connection_listener: Callable[[], None] | None = None

    def registered(self, socket_client: SocketClient) -> None:
        """Called when a controller is registered."""
        super().registered(socket_client)
        self._remove_connection_listener = socket_client.register_connection_listener(
            self
        )

    def unregistered(self) -> None:
        """Called when a controller is unregistered."""
        super().unregistered()
        self._stop()

    def tear_down(self) -> None:
        """Called when we are shutting down."""
        super().tear_down()
        self._stop()

    def _stop(self) -> None:
        """Stop listening to the connection and fail pending requests."""
        if self._remove_connection_listener:
            self._remove_connection_listener()
            self._remove_connection_listener = None
        self._fail_pending()

    def new_connection_status(self, status: ConnectionStatus) -> None:
        """Fail pending requests, the replies are lost with the connection."""
        if status.status != CONNECTION_STATUS_CONNECTED:
            self._fail_pending()

    def _fail_pending(self) -> None:
        """Call the callbacks of pending requests with failure."""
        with self._lock:
            callbacks = list(self._callbacks.values())
            self._callbacks = {}
        for callback_function in callbacks:
            callback_function(False, None)

    def request_eureka_info(
        self, params: list[str], *, callback_function: CallbackType
    ) -> None:
        """Request the eureka_info with the params, e.g. ["multizone"].

        callback_function is called with the reply, the eureka_info is in its
        data.
        """
        with self._lock:
            self._request_id += 1
            request_id = self._request_id
            self._callbacks[request_id] = callback_function

        def handle_sent(msg_sent: bool, _response: dict | None) -> None:
            if msg_sent:
                return
            with self._lock:
                pending = self._callbacks.pop(request_id, None)
            if pending:
                pending(False, None)

        self.send_message(
            {
                MESSAGE_TYPE: TYPE_EUREKA_INFO,
                SETUP_REQUEST_ID: request_id,
                "data": {"params": params},
            },
            callback_function=handle_sent,
            no_add_request_id=True,
        )

    def get_eureka_info(
        self, params: list[str], timeout: float = REQUEST_TIMEOUT
    ) -> EurekaInfo:
        """Return the eureka_info with the params, e.g. ["multizone"]."""
        response_handler = WaitResponse(timeout, TYPE_EUREKA_INFO)
        self.request_eureka_info(params, callback_function=response_handler.callback)
        response_handler.wait_response()
        if TYPE_CHECKING:
            assert response_handler.response
        return cast(EurekaInfo, response_handler.response["data"])

    def receive_message(self, _message: CastMessage, data: dict) -> bool:
        """Called when a setup message is received."""
        if data.get(MESSAGE_TYPE) != TYPE_EUREKA_INFO:
            return False
        request_id = data.get(SETUP_REQUEST_ID)
        if not isinstance(request_id, int):
            return False
        with self._lock:
            callback_function = self._callbacks.pop(request_id, None)
        if callback_function is None:
            return False
        if data.get("response_code") != HTTPStatus.OK:
            self.logger.debug("eureka_info failed: %s", data)
            callback_function(False, data)
            return True
        if not isinstance(data.get("data"), dict):
            self.logger.debug("eureka_info reply has no data: %s", data)
            callback_function(False, data)
            return True
        callback_function(True, data)
        return True
