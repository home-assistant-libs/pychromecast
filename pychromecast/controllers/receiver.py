"""
Provides a controller for controlling the default media players
on the Chromecast.
"""

import abc
from dataclasses import dataclass
from functools import partial

from ..const import (
    CAST_TYPE_AUDIO,
    CAST_TYPE_CHROMECAST,
    CAST_TYPE_GROUP,
    MESSAGE_TYPE,
    REQUEST_ID,
    REQUEST_TIMEOUT,
    SESSION_ID,
)
from ..generated.cast_channel_pb2 import (  # pylint: disable=no-name-in-module
    CastMessage,
)
from ..response_handler import WaitResponse, chain_on_success
from . import BaseController, CallbackType

APP_ID = "appId"
ERROR_REASON = "reason"

NS_RECEIVER = "urn:x-cast:com.google.cast.receiver"

TYPE_GET_STATUS = "GET_STATUS"
TYPE_RECEIVER_STATUS = "RECEIVER_STATUS"
TYPE_LAUNCH = "LAUNCH"
TYPE_LAUNCH_ERROR = "LAUNCH_ERROR"

LAUNCH_CANCELLED = "CANCELLED"

VOLUME_CONTROL_TYPE_ATTENUATION = "attenuation"
VOLUME_CONTROL_TYPE_FIXED = "fixed"
VOLUME_CONTROL_TYPE_MASTER = "master"


@dataclass(frozen=True)
class CastStatus:
    """Cast status container."""

    is_active_input: bool | None
    is_stand_by: bool | None
    volume_level: float
    volume_muted: bool
    app_id: str | None
    display_name: str | None
    namespaces: list[str]
    session_id: str | None
    transport_id: str | None
    status_text: str
    icon_url: str | None
    volume_control_type: str


@dataclass(frozen=True)
class LaunchFailure:
    """Launch failure container."""

    reason: str | None
    app_id: str | None
    request_id: int | None


class CastStatusListener(abc.ABC):
    """Listener for receiving cast status events."""

    @abc.abstractmethod
    def new_cast_status(self, status: CastStatus) -> None:
        """Updated cast status."""


class LaunchErrorListener(abc.ABC):
    """Listener for receiving launch error events."""

    @abc.abstractmethod
    def new_launch_error(self, status: LaunchFailure) -> None:
        """Launch error."""


class ReceiverController(BaseController):
    """
    Controller to interact with the Chromecast platform.

    :param cast_type: Type of Chromecast device.
    """

    def __init__(self, cast_type: str = CAST_TYPE_CHROMECAST) -> None:
        super().__init__(NS_RECEIVER, target_platform=True)

        self.status: CastStatus | None = None
        self.launch_failure: LaunchFailure | None = None
        self.cast_type = cast_type

        self._status_listeners: list[CastStatusListener] = []
        self._launch_error_listeners: list[LaunchErrorListener] = []

    def disconnected(self) -> None:
        """Called when disconnected. Will erase status."""
        self.logger.info("Receiver:channel_disconnected")
        self.status = None

    @property
    def app_id(self) -> str | None:
        """Convenience method to retrieve current app id."""
        return self.status.app_id if self.status else None

    def receive_message(self, _message: CastMessage, data: dict) -> bool:
        """
        Called when a receiver message is received.

        data is message.payload_utf8 interpreted as a JSON dict.
        """
        if data[MESSAGE_TYPE] == TYPE_RECEIVER_STATUS:
            self._process_get_status(data)

            return True

        if data[MESSAGE_TYPE] == TYPE_LAUNCH_ERROR:
            self._process_launch_error(data)

            return True

        return False

    def register_status_listener(self, listener: CastStatusListener) -> None:
        """Register a status listener for when a new Chromecast status
        has been received. Listeners will be called with
        listener.new_cast_status(status)"""
        self._status_listeners.append(listener)

    def register_launch_error_listener(self, listener: LaunchErrorListener) -> None:
        """Register a listener for when a new launch error message
        has been received. Listeners will be called with
        listener.new_launch_error(launch_failure)"""
        self._launch_error_listeners.append(listener)

    def update_status(
        self,
        *,
        callback_function: CallbackType | None = None,
    ) -> None:
        """Sends a message to the Chromecast to update the status."""
        self.logger.debug("Receiver:Updating status")
        self.send_message(
            {MESSAGE_TYPE: TYPE_GET_STATUS}, callback_function=callback_function
        )

    def launch_app(
        self,
        app_id: str,
        *,
        force_launch: bool = False,
        callback_function: CallbackType | None = None,
    ) -> None:
        """Launches an app on the Chromecast.

        Will only launch if it is not currently running unless
        force_launch=True."""

        if not force_launch and self.status is None:
            self.update_status(
                callback_function=chain_on_success(
                    partial(self._send_launch_message, app_id, force_launch),
                    callback_function,
                )
            )

        else:
            self._send_launch_message(app_id, force_launch, callback_function)

    def _send_launch_message(
        self,
        app_id: str,
        force_launch: bool,
        callback_function: CallbackType | None,
        *,
        retry_on_cancelled_error: bool = True,
    ) -> None:
        if force_launch or self.app_id != app_id:
            self.logger.info("Receiver:Launching app %s", app_id)

            self.launch_failure = None

            def handle_launch_response(msg_sent: bool, response: dict | None) -> None:
                if (
                    msg_sent  # pylint: disable=too-many-boolean-expressions
                    and response
                    and response.get(MESSAGE_TYPE) == TYPE_LAUNCH_ERROR
                    and response.get(ERROR_REASON) == LAUNCH_CANCELLED
                    and not self._launch_error_listeners
                    and retry_on_cancelled_error
                ):
                    self.logger.info(
                        "Receiver:Launching app %s failed, retrying once", app_id
                    )
                    self._send_launch_message(
                        app_id,
                        force_launch,
                        callback_function,
                        retry_on_cancelled_error=False,
                    )
                    return

                if not callback_function:
                    return

                if not msg_sent or not response:
                    callback_function(False, response)
                    return

                if response[MESSAGE_TYPE] == TYPE_RECEIVER_STATUS:
                    callback_function(True, response)
                    return

                callback_function(False, response)

            self.send_message(
                {MESSAGE_TYPE: TYPE_LAUNCH, APP_ID: app_id},
                callback_function=handle_launch_response,
            )
        else:
            self.logger.info("Not launching app %s - already running", app_id)
            if callback_function:
                callback_function(True, None)

    def stop_app(
        self,
        *,
        callback_function: CallbackType | None = None,
    ) -> None:
        """Stops the current running app on the Chromecast."""
        self.logger.info("Receiver:Stopping current app '%s'", self.app_id)
        return self.send_message(
            {MESSAGE_TYPE: "STOP"},
            inc_session_id=True,
            callback_function=callback_function,
        )

    def set_volume(self, volume: float, timeout: float = REQUEST_TIMEOUT) -> float:
        """Allows to set volume. Should be value between 0..1.
        Returns the new volume.

        """
        volume = min(max(0, volume), 1)
        self.logger.info("Receiver:setting volume to %.2f", volume)
        response_handler = WaitResponse(timeout, "set volume")
        self.send_message(
            {MESSAGE_TYPE: "SET_VOLUME", "volume": {"level": volume}},
            callback_function=response_handler.callback,
        )
        response_handler.wait_response()
        return volume

    def set_volume_muted(self, muted: bool, timeout: float = REQUEST_TIMEOUT) -> None:
        """Allows to mute volume."""
        response_handler = WaitResponse(timeout, "mute volume")
        self.send_message(
            {MESSAGE_TYPE: "SET_VOLUME", "volume": {"muted": muted}},
            callback_function=response_handler.callback,
        )
        response_handler.wait_response()

    @staticmethod
    def _parse_status(data: dict, cast_type: str) -> CastStatus:
        """
        Parses a STATUS message and returns a CastStatus object.

        :type data: dict
        :param cast_type: Type of Chromecast.
        :rtype: CastStatus
        """
        status_data: dict = data.get("status", {})

        volume_data: dict = status_data.get("volume", {})

        try:
            app_data: dict = status_data["applications"][0]
        except (KeyError, IndexError):
            app_data = {}

        is_audio = cast_type in (CAST_TYPE_AUDIO, CAST_TYPE_GROUP)

        status = CastStatus(
            data.get("isActiveInput", None if is_audio else False),
            data.get("isStandBy", None if is_audio else True),
            volume_data.get("level", 1.0),
            volume_data.get("muted", False),
            app_data.get(APP_ID),
            app_data.get("displayName"),
            [item["name"] for item in app_data.get("namespaces", [])],
            app_data.get(SESSION_ID),
            app_data.get("transportId"),
            app_data.get("statusText", ""),
            app_data.get("iconUrl"),
            volume_data.get("controlType", VOLUME_CONTROL_TYPE_ATTENUATION),
        )
        return status

    def _process_get_status(self, data: dict) -> None:
        """Processes a received STATUS message and notifies listeners."""
        status = self._parse_status(data, self.cast_type)
        self.status = status

        self.logger.debug("Received status: %s", self.status)

        for listener in self._status_listeners:
            try:
                listener.new_cast_status(self.status)
            except Exception:  # pylint: disable=broad-except
                self.logger.exception(
                    "Exception thrown when calling cast status listener"
                )

    @staticmethod
    def _parse_launch_error(data: dict) -> LaunchFailure:
        """
        Parses a LAUNCH_ERROR message and returns a LaunchFailure object.

        :type data: dict
        :rtype: LaunchFailure
        """
        return LaunchFailure(
            data.get(ERROR_REASON, None), data.get(APP_ID), data.get(REQUEST_ID)
        )

    def _process_launch_error(self, data: dict) -> None:
        """
        Processes a received LAUNCH_ERROR message and notifies listeners.
        """
        launch_failure = self._parse_launch_error(data)
        self.launch_failure = launch_failure

        self.logger.debug("Launch status: %s", launch_failure)

        for listener in self._launch_error_listeners:
            try:
                listener.new_launch_error(launch_failure)
            except Exception:  # pylint: disable=broad-except
                self.logger.exception(
                    "Exception thrown when calling launch error listener"
                )

    def tear_down(self) -> None:
        """Called when controller is destroyed."""
        super().tear_down()

        self.status = None
        self.launch_failure = None

        self._status_listeners = []
