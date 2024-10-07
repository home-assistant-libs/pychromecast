"""Controller to send and respond to heartbeat messages."""

from __future__ import annotations

import time

from . import BaseController

from ..const import MESSAGE_TYPE, PLATFORM_DESTINATION_ID
from ..error import ControllerNotRegistered, NotConnected, PyChromecastStopped

# pylint: disable-next=no-name-in-module
from ..generated.cast_channel_pb2 import CastMessage

NS_HEARTBEAT = "urn:x-cast:com.google.cast.tp.heartbeat"

TYPE_PING = "PING"
TYPE_PONG = "PONG"

HB_PING_TIME = 10
HB_PONG_TIME = 10


class HeartbeatController(BaseController):
    """Controller to send and respond to heartbeat messages."""

    def __init__(self) -> None:
        super().__init__(NS_HEARTBEAT, target_platform=True)
        self.last_ping = 0.0
        self.last_pong = time.time()

    def receive_message(self, _message: CastMessage, data: dict) -> bool:
        """
        Called when a heartbeat message is received.

        data is message.payload_utf8 interpreted as a JSON dict.
        """
        if self._socket_client is None:
            raise ControllerNotRegistered

        if self._socket_client.is_stopped:
            return True

        if data[MESSAGE_TYPE] == TYPE_PING:
            try:
                self._socket_client.send_message(
                    PLATFORM_DESTINATION_ID,
                    self.namespace,
                    {MESSAGE_TYPE: TYPE_PONG},
                    no_add_request_id=True,
                )
            except PyChromecastStopped:
                self._socket_client.logger.debug(
                    "Heartbeat error when sending response, "
                    "Chromecast connection has stopped"
                )

            return True

        if data[MESSAGE_TYPE] == TYPE_PONG:
            self.reset()
            return True

        return False

    def ping(self) -> None:
        """Send a ping message."""
        if self._socket_client is None:
            raise ControllerNotRegistered

        self.last_ping = time.time()
        try:
            self.send_message({MESSAGE_TYPE: TYPE_PING})
        except NotConnected:
            self._socket_client.logger.error(
                "Chromecast is disconnected. Cannot ping until reconnected."
            )

    def reset(self) -> None:
        """Reset expired counter."""
        self.last_pong = time.time()

    def is_expired(self) -> bool:
        """Indicates if connection has expired."""
        if time.time() - self.last_ping > HB_PING_TIME:
            self.ping()

        return (time.time() - self.last_pong) > HB_PING_TIME + HB_PONG_TIME
