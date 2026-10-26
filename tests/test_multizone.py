"""Tests for the multizone controller."""

from unittest.mock import MagicMock
from uuid import UUID

import pytest

from pychromecast.controllers.multizone import (
    MultizoneController,
    MultiZoneControllerListener,
    PlaybackSession,
    PlaybackSessionUpdate,
    SessionEndpoint,
)
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
