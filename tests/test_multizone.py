"""Tests for the multizone controller."""

from functools import partial
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from pychromecast.controllers import add_listener
from pychromecast.controllers.multizone import (
    MultizoneController,
    MultiZoneControllerListener,
    MultizoneManager,
    MultiZoneManagerListener,
    PlaybackSession,
    PlaybackSessionUpdate,
    SessionEndpoint,
)
from pychromecast.const import CAST_TYPE_GROUP
from pychromecast.socket_client import CONNECTION_STATUS_CONNECTED
from pychromecast.models import CastInfo

GROUP_UUID = "9a4683f8-a265-4ec7-aab1-a70cb50f4ca7"
KITCHEN_UUID = "be209f09-0f6a-4596-ac1a-16a77670692b"
BACK_ROOM_UUID = "2b514019-b9fa-43b5-a740-b4c3f8882918"


def _status(**extra: object) -> dict:
    return {
        "type": "MULTIZONE_STATUS",
        "requestId": 1,
        "status": {
            "devices": [
                {"deviceId": KITCHEN_UUID, "name": "Kitchen", "capabilities": 196612}
            ],
            "isMultichannel": False,
            **extra,
        },
    }


def _controller() -> tuple[MultizoneController, MagicMock]:
    controller = MultizoneController(UUID(GROUP_UUID))
    listener = MagicMock(spec=MultiZoneControllerListener)
    controller.register_listener(listener)
    return controller, listener


def test_playback_session_from_status() -> None:
    """Test playback session flags are read from multizone status."""
    controller, listener = _controller()
    assert controller.playback_session is None

    controller.receive_message(
        MagicMock(),
        _status(
            playbackSession={
                "appAllowsGrouping": True,
                "isVideoContent": False,
                "streamTransferSupported": True,
            }
        ),
    )
    assert controller.members == [KITCHEN_UUID]
    assert controller.playback_session == PlaybackSession(
        app_allows_grouping=True,
        is_video_content=False,
        stream_transfer_supported=True,
    )
    listener.multizone_status_received.assert_called_once()

    # No session attached any more
    controller.receive_message(MagicMock(), _status())
    assert controller.playback_session is None


def test_playback_session_reset() -> None:
    """Test playback session is cleared together with members."""
    controller, _ = _controller()
    controller.receive_message(
        MagicMock(), _status(playbackSession={"appAllowsGrouping": False})
    )
    assert controller.playback_session == PlaybackSession(False, None, None)

    controller.reset_members()
    assert controller.playback_session is None
    assert not controller.members


def test_playback_session_updated() -> None:
    """Test session updates are parsed and passed to listeners."""
    controller, listener = _controller()
    assert controller.receive_message(
        MagicMock(),
        {
            "type": "PLAYBACK_SESSION_UPDATED",
            "requestId": 5,
            "name": "Kitchen + 1",
            "changedDevices": [BACK_ROOM_UUID.replace("-", "")],
            "failedDevices": [],
            "sessionEndpoint": {
                "deviceId": GROUP_UUID,
                "ipAddress": "192.168.0.13",
                "port": 32046,
                "sessionId": "9e63447a-e514-4a79-a22c-2afa00eea9c1",
            },
        },
    )
    listener.multizone_playback_session_updated.assert_called_once_with(
        PlaybackSessionUpdate(
            name="Kitchen + 1",
            changed_devices=[BACK_ROOM_UUID],
            failed_devices=[],
            session_endpoint=SessionEndpoint(
                device_id=GROUP_UUID,
                host="192.168.0.13",
                port=32046,
                session_id="9e63447a-e514-4a79-a22c-2afa00eea9c1",
            ),
        )
    )


@pytest.mark.parametrize(
    ("endpoint", "playback_session"),
    [
        # The session moved away
        (KITCHEN_UUID, None),
        # The session moved here
        (GROUP_UUID, PlaybackSession(True, None, None)),
    ],
)
def test_playback_session_moved(
    endpoint: str, playback_session: PlaybackSession | None
) -> None:
    """Test the playback session is cleared when the session moves away."""
    controller, _ = _controller()
    controller.receive_message(
        MagicMock(), _status(playbackSession={"appAllowsGrouping": True})
    )

    controller.receive_message(
        MagicMock(),
        {
            "type": "PLAYBACK_SESSION_UPDATED",
            "requestId": 0,
            "changedDevices": [],
            "failedDevices": [],
            "sessionEndpoint": {
                "deviceId": endpoint,
                "ipAddress": "192.168.0.13",
                "port": 32046,
                "sessionId": "9e63447a-e514-4a79-a22c-2afa00eea9c1",
            },
        },
    )

    assert controller.playback_session == playback_session


def test_playback_session_updated_without_endpoint() -> None:
    """Test session update where the endpoint did not move."""
    controller, listener = _controller()
    controller.receive_message(
        MagicMock(),
        {
            "type": "PLAYBACK_SESSION_UPDATED",
            "requestId": 0,
            "changedDevices": [],
        },
    )
    listener.multizone_playback_session_updated.assert_called_once_with(
        PlaybackSessionUpdate(
            name="", changed_devices=[], failed_devices=[], session_endpoint=None
        )
    )


def test_listener_without_session_callback() -> None:
    """Test listeners written before the session callback existed keep working."""

    class OldListener(MultiZoneControllerListener):
        def multizone_member_added(self, group_uuid: str) -> None:
            pass

        def multizone_member_removed(self, group_uuid: str) -> None:
            pass

        def multizone_status_received(self) -> None:
            pass

    controller = MultizoneController(UUID(GROUP_UUID))
    controller.register_listener(OldListener())
    assert controller.receive_message(
        MagicMock(), {"type": "PLAYBACK_SESSION_UPDATED", "requestId": 0}
    )


SESSION_ID = "9e63447a-e514-4a79-a22c-2afa00eea9c1"


def _cast_info(uuid: str, host: str) -> CastInfo:
    return CastInfo(set(), UUID(uuid), None, None, host, 8009, "audio", None)


def _registered_controller() -> tuple[MultizoneController, MagicMock]:
    controller = MultizoneController(UUID(GROUP_UUID))
    socket_client = MagicMock()
    controller.registered(socket_client)
    return controller, socket_client.send_platform_message


def test_set_playback_devices_message() -> None:
    """Test the SET_PLAYBACK_DEVICES message."""
    controller, send = _registered_controller()

    controller.set_playback_devices(
        SESSION_ID,
        [
            _cast_info(KITCHEN_UUID, "192.168.0.13"),
            _cast_info(BACK_ROOM_UUID, "192.168.0.11"),
        ],
        session_name="Kitchen and back room",
    )

    send.assert_called_once()
    namespace, message = send.call_args.args
    assert namespace == "urn:x-cast:com.google.cast.multizone"
    assert message == {
        "type": "SET_PLAYBACK_DEVICES",
        "sessionId": SESSION_ID,
        "deviceList": [
            {"deviceId": KITCHEN_UUID, "ipAddress": "192.168.0.13", "port": 8009},
            {"deviceId": BACK_ROOM_UUID, "ipAddress": "192.168.0.11", "port": 8009},
        ],
        "sessionName": "Kitchen and back room",
    }


def test_set_playback_devices_requires_a_device() -> None:
    """Test a session can't be set to play on no devices."""
    controller, send = _registered_controller()

    with pytest.raises(ValueError):
        controller.set_playback_devices(SESSION_ID, [])
    send.assert_not_called()


@pytest.mark.parametrize(
    ("msg_sent", "response", "success"),
    [
        (
            True,
            {"type": "PLAYBACK_SESSION_UPDATED", "failedDevices": []},
            True,
        ),
        (
            True,
            {"type": "PLAYBACK_SESSION_UPDATED", "failedDevices": [KITCHEN_UUID]},
            False,
        ),
        (True, {"type": "INVALID_REQUEST", "reason": "INVALID_SESSION_ID"}, False),
        (True, {"type": "INVALID_REQUEST"}, False),
        (False, None, False),
    ],
)
def test_set_playback_devices_response(
    msg_sent: bool, response: dict | None, success: bool
) -> None:
    """Test the callback reports whether all devices were changed."""
    controller, send = _registered_controller()
    callback = MagicMock()

    controller.set_playback_devices(
        SESSION_ID,
        [_cast_info(KITCHEN_UUID, "192.168.0.13")],
        callback_function=callback,
    )
    send.call_args.kwargs["callback_function"](msg_sent, response)

    callback.assert_called_once_with(success, response)


SPEAKER_A = "6a1c3e2f-5b7d-4e8a-9c0b-1d2e3f4a5b6c"
SPEAKER_B = "7b2d4f3a-6c8e-4f9b-8d1c-2e3f4a5b6c7d"
SESSION = "1546815f-47eb-4c7d-8216-181f1197f05b"
PLAYBACK_SESSION = {
    "appAllowsGrouping": True,
    "isVideoContent": False,
    "streamTransferSupported": True,
}


class FakeEndpoint:
    """A connected cast device or group which answers multizone requests."""

    def __init__(
        self,
        uuid: str,
        session_id: str | None,
        members: list[str],
        playback_session: dict | None,
        host: str = "192.0.2.1",
    ) -> None:
        self.cast = MagicMock(uuid=UUID(uuid), cast_info=_cast_info(uuid, host))
        self.cast.status.session_id = session_id
        self.cast.register_handler.side_effect = self._register
        self._status_listeners: list[Any] = []
        self._connection_listeners: list[Any] = []
        self.cast.register_status_listener.side_effect = partial(
            add_listener, self._status_listeners
        )
        self.cast.register_connection_listener.side_effect = partial(
            add_listener, self._connection_listeners
        )
        self.members = members
        self.playback_session = playback_session
        self.response: dict = {"type": "INVALID_REQUEST"}
        self.sent: list[dict] = []
        self.controller: MultizoneController | None = None

    def _register(self, controller: MultizoneController) -> None:
        self.controller = controller
        socket_client = MagicMock()
        socket_client.send_platform_message.side_effect = self._receive
        controller.registered(socket_client)

    def connect(self) -> None:
        """Report the connection and the receiver status, like a Chromecast."""
        for listener in self._connection_listeners:
            listener.new_connection_status(
                MagicMock(status=CONNECTION_STATUS_CONNECTED)
            )
        self.new_cast_status()

    def new_cast_status(self) -> None:
        """Report the receiver status."""
        for listener in self._status_listeners:
            listener.new_cast_status(self.cast.status)

    def _receive(self, _namespace: str, data: dict, **kwargs: Any) -> None:
        assert self.controller is not None
        self.sent.append(data)
        if data["type"] == "GET_STATUS":
            status: dict = {
                "devices": [{"deviceId": m, "name": m} for m in self.members]
            }
            if self.playback_session is not None:
                status["playbackSession"] = self.playback_session
            response = {"type": "MULTIZONE_STATUS", "requestId": 1, "status": status}
            self.controller.receive_message(MagicMock(), response)
        else:
            response = self.response
        if callback_function := kwargs.get("callback_function"):
            callback_function(True, response)

    def device_list(self) -> set[tuple[str, str]]:
        """Return the devices and addresses of the last SET_PLAYBACK_DEVICES."""
        assert self.sent[-1]["type"] == "SET_PLAYBACK_DEVICES"
        return {
            (device["deviceId"], device["ipAddress"])
            for device in self.sent[-1]["deviceList"]
        }


def _speaker_a(
    session_id: str | None = SESSION,
    playback_session: dict | None = None,
    owner: bool = True,
) -> FakeEndpoint:
    if owner and playback_session is None:
        playback_session = PLAYBACK_SESSION
    return FakeEndpoint(
        SPEAKER_A, session_id, [SPEAKER_A], playback_session, "192.0.2.10"
    )


def _speaker_b(session_id: str | None = None) -> FakeEndpoint:
    return FakeEndpoint(SPEAKER_B, session_id, [SPEAKER_B], None, "192.0.2.11")


def _group(members: list[str]) -> FakeEndpoint:
    # Hosted by speaker A
    return FakeEndpoint(GROUP_UUID, SESSION, members, PLAYBACK_SESSION, "192.0.2.10")


def _manager(
    devices: list[FakeEndpoint], groups: list[FakeEndpoint] | None = None
) -> MultizoneManager:
    manager = MultizoneManager()
    for device in devices:
        manager.add_multizone(device.cast)
        device.connect()
    for group in groups or []:
        group.cast.cast_type = CAST_TYPE_GROUP
        manager.add_multizone(group.cast)
        group.connect()
    return manager


def test_multizone_manager_members() -> None:
    """Test the members of managed groups are exposed."""
    group = FakeEndpoint(GROUP_UUID, None, [], None)
    group.cast.cast_type = CAST_TYPE_GROUP
    manager = MultizoneManager()
    manager.add_multizone(group.cast)
    group.connect()
    assert manager.get_multizone_members(UUID(GROUP_UUID)) == []

    group.members = [KITCHEN_UUID]
    group.connect()

    assert manager.get_multizone_members(UUID(GROUP_UUID)) == [KITCHEN_UUID]
    # The listeners are passed group uuids as strings
    assert manager.get_multizone_members(GROUP_UUID) == [KITCHEN_UUID]


def test_group_told_to_members() -> None:
    """Test the members of a group are told about it and its status."""
    group = _group([SPEAKER_B, SPEAKER_A])
    group.cast.cast_type = CAST_TYPE_GROUP
    manager = MultizoneManager()
    listener = MagicMock(spec=MultiZoneManagerListener)
    manager.register_listener(UUID(SPEAKER_A), listener)
    manager.add_multizone(group.cast)
    group.connect()

    listener.added_to_multizone.assert_called_once_with(GROUP_UUID)
    assert manager.get_multizone_memberships(UUID(SPEAKER_A)) == [GROUP_UUID]
    listener.multizone_new_cast_status.assert_called_with(GROUP_UUID, group.cast.status)
    media_listener = group.cast.media_controller.register_status_listener.call_args
    media_status = MagicMock()
    media_listener.args[0].new_media_status(media_status)
    listener.multizone_new_media_status.assert_called_once_with(
        GROUP_UUID, media_status
    )

    manager.remove_multizone(UUID(GROUP_UUID))
    listener.removed_from_multizone.assert_called_once_with(GROUP_UUID)
    assert manager.get_multizone_memberships(UUID(SPEAKER_A)) == []


def test_sessions_changed_reported() -> None:
    """Test manager listeners are told when sessions may have changed."""
    speaker_a = _speaker_a(None)
    manager = _manager([speaker_a])
    listener = MagicMock(spec=MultiZoneManagerListener)
    manager.register_listener(UUID(SPEAKER_A), listener)

    speaker_a.cast.status.session_id = SESSION
    speaker_a.new_cast_status()

    # Once for the new session and once for the status
    assert listener.multizone_sessions_changed.call_count == 2


def test_removed_device_not_tracked() -> None:
    """Test a removed device no longer requests status."""
    speaker_a = _speaker_a(None)
    manager = _manager([speaker_a])
    manager.remove_multizone(UUID(SPEAKER_A))
    speaker_a.sent.clear()

    speaker_a.cast.status.session_id = SESSION
    speaker_a.new_cast_status()

    assert not speaker_a.sent


def test_member_changes_dont_request_status() -> None:
    """Test the members reported by a status don't request it again."""
    group = FakeEndpoint(GROUP_UUID, None, [SPEAKER_B, SPEAKER_A], None)
    _manager([], [group])

    assert [data["type"] for data in group.sent] == ["GET_STATUS"]


@pytest.mark.parametrize("group_uuid", [UUID(GROUP_UUID), GROUP_UUID])
def test_remove_group(group_uuid: UUID | str) -> None:
    """Test members are told a removed group is gone, and it's no longer tracked."""
    group = _group([SPEAKER_B, SPEAKER_A])
    manager = _manager([], [group])
    listener = MagicMock(spec=MultiZoneManagerListener)
    manager.register_listener(UUID(SPEAKER_A), listener)

    manager.remove_multizone(group_uuid)

    listener.removed_from_multizone.assert_called_once_with(GROUP_UUID)
    listener.multizone_sessions_changed.assert_called_once_with()
    group.sent.clear()
    group.connect()
    assert not group.sent
    listener.multizone_new_cast_status.assert_not_called()
