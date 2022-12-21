"""
Provides a controller for controlling the default media players
on the Chromecast.
"""
import abc

from collections import namedtuple

from ..const import (
    CAST_TYPE_AUDIO,
    CAST_TYPE_CHROMECAST,
    CAST_TYPE_GROUP,
    MESSAGE_TYPE,
    REQUEST_ID,
    SESSION_ID,
)
from . import BaseController

APP_ID = "appId"
ERROR_REASON = "reason"

NS_RECEIVER = "urn:x-cast:com.google.cast.receiver"

TYPE_GET_STATUS = "GET_STATUS"
TYPE_RECEIVER_STATUS = "RECEIVER_STATUS"
TYPE_LAUNCH = "LAUNCH"
TYPE_LAUNCH_ERROR = "LAUNCH_ERROR"

VOLUME_CONTROL_TYPE_ATTENUATION = "attenuation"
VOLUME_CONTROL_TYPE_FIXED = "fixed"
VOLUME_CONTROL_TYPE_MASTER = "master"

CastStatus = namedtuple(
    "CastStatus",
    [
        "is_active_input",
        "is_stand_by",
        "volume_level",
        "volume_muted",
        "app_id",
        "display_name",
        "namespaces",
        "session_id",
        "transport_id",
        "status_text",
        "icon_url",
        "volume_control_type",
    ],
)

LaunchFailure = namedtuple("LaunchStatus", ["reason", "app_id", "request_id"])


class CastStatusListener(abc.ABC):
    """Listener for receiving cast status events."""

    @abc.abstractmethod
    def new_cast_status(self, status: CastStatus):
        """Updated cast status."""


class LaunchErrorListener(abc.ABC):
    """Listener for receiving launch error events."""

    @abc.abstractmethod
    def new_launch_error(self, status: LaunchFailure):
        """Launch error."""


class ReceiverController(BaseController):
    """
    Controller to interact with the Chromecast platform.

    :param cast_type: Type of Chromecast device.
    """

    def __init__(self, cast_type=CAST_TYPE_CHROMECAST):
        super().__init__(NS_RECEIVER, target_platform=True)

        self.status = None
        self.launch_failure = None
        self.app_to_launch = None
        self.cast_type = cast_type
        self.app_launch_event_function = None

        self._status_listeners = []
        self._launch_error_listeners = []

    def disconnected(self):
        """Called when disconnected. Will erase status."""
        self.logger.info("Receiver:channel_disconnected")
        self.status = None

    @property
    def app_id(self):
        """Convenience method to retrieve current app id."""
        return self.status.app_id if self.status else None

    def receive_message(self, _message, data: dict):
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

    def register_status_listener(self, listener: CastStatusListener):
        """Register a status listener for when a new Chromecast status
        has been received. Listeners will be called with
        listener.new_cast_status(status)"""
        self._status_listeners.append(listener)

    def register_launch_error_listener(self, listener: LaunchErrorListener):
        """Register a listener for when a new launch error message
        has been received. Listeners will be called with
        listener.new_launch_error(launch_failure)"""
        self._launch_error_listeners.append(listener)

    def update_status(self, callback_function_param=False):
        """Sends a message to the Chromecast to update the status."""
        self.logger.debug("Receiver:Updating status")
        self.send_message(
            {MESSAGE_TYPE: TYPE_GET_STATUS}, callback_function=callback_function_param
        )

    def launch_app(self, app_id, force_launch=False, callback_function=False):
        """Launches an app on the Chromecast.

        Will only launch if it is not currently running unless
        force_launch=True."""

        if not force_launch and self.status is None:
            self.update_status(
                lambda response: self._send_launch_message(
                    app_id, force_launch, callback_function
                )
            )
        else:
            self._send_launch_message(app_id, force_launch, callback_function)

    def _send_launch_message(self, app_id, force_launch=False, callback_function=False):
        if force_launch or self.app_id != app_id:
            self.logger.info("Receiver:Launching app %s", app_id)

            self.app_to_launch = app_id
            self.app_launch_event_function = callback_function
            self.launch_failure = None

            self.send_message({MESSAGE_TYPE: TYPE_LAUNCH, APP_ID: app_id})
        else:
            self.logger.info("Not launching app %s - already running", app_id)
            if callback_function:
                callback_function()

    def stop_app(self, callback_function_param=False):
        """Stops the current running app on the Chromecast."""
        self.logger.info("Receiver:Stopping current app '%s'", self.app_id)
        return self.send_message(
            {MESSAGE_TYPE: "STOP"},
            inc_session_id=True,
            callback_function=callback_function_param,
        )

    def set_volume(self, volume):
        """Allows to set volume. Should be value between 0..1.
        Returns the new volume.

        """
        volume = min(max(0, volume), 1)
        self.logger.info("Receiver:setting volume to %.1f", volume)
        self.send_message({MESSAGE_TYPE: "SET_VOLUME", "volume": {"level": volume}})
        return volume

    def set_volume_muted(self, muted):
        """Allows to mute volume."""
        self.send_message({MESSAGE_TYPE: "SET_VOLUME", "volume": {"muted": muted}})

    @staticmethod
    def _parse_status(data, cast_type):
        """
        Parses a STATUS message and returns a CastStatus object.

        :type data: dict
        :param cast_type: Type of Chromecast.
        :rtype: CastStatus
        """
        data = data.get("status", {})

        volume_data = data.get("volume", {})

        try:
            app_data = data["applications"][0]
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

    def _process_get_status(self, data):
        """Processes a received STATUS message and notifies listeners."""
        status = self._parse_status(data, self.cast_type)
        is_new_app = self.app_id != status.app_id and self.app_to_launch
        self.status = status

        self.logger.debug("Received status: %s", self.status)
        self._report_status()

        if is_new_app and self.app_to_launch == self.app_id:
            self.app_to_launch = None
            if self.app_launch_event_function:
                self.logger.debug("Start app_launch_event_function...")
                self.app_launch_event_function()
                self.app_launch_event_function = None

    def _report_status(self):
        """Reports the current status to all listeners."""
        for listener in self._status_listeners:
            try:
                listener.new_cast_status(self.status)
            except Exception:  # pylint: disable=broad-except
                self.logger.exception(
                    "Exception thrown when calling cast status listener"
                )

    @staticmethod
    def _parse_launch_error(data):
        """
        Parses a LAUNCH_ERROR message and returns a LaunchFailure object.

        :type data: dict
        :rtype: LaunchFailure
        """
        return LaunchFailure(
            data.get(ERROR_REASON, None), data.get(APP_ID), data.get(REQUEST_ID)
        )

    def _process_launch_error(self, data):
        """
        Processes a received LAUNCH_ERROR message and notifies listeners.
        """
        launch_failure = self._parse_launch_error(data)
        self.launch_failure = launch_failure

        if self.app_to_launch:
            self.app_to_launch = None

        self.logger.debug("Launch status: %s", launch_failure)

        for listener in self._launch_error_listeners:
            try:
                listener.new_launch_error(launch_failure)
            except Exception:  # pylint: disable=broad-except
                self.logger.exception(
                    "Exception thrown when calling launch error listener"
                )

    def tear_down(self):
        """Called when controller is destroyed."""
        super().tear_down()

        self.status = None
        self.launch_failure = None
        self.app_to_launch = None

        self._status_listeners = []
