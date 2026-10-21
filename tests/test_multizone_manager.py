"""Tests for the multizone manager."""

from unittest.mock import MagicMock
from uuid import UUID

from pychromecast.controllers.multizone import (
    MultizoneController,
    MultizoneManager,
    MultiZoneManagerListener,
)

GROUP_UUID = UUID("9a4683f8-a265-4ec7-aab1-a70cb50f4ca7")
MEMBER_UUID = UUID("8b6ab22b-b85b-5c3e-a5b4-be0c7e00f299")


def test_member_added_gets_group_status() -> None:
    """Test a member added to a group gets the group's current status."""
    manager = MultizoneManager()
    group_cast = MagicMock(uuid=GROUP_UUID)
    manager.add_multizone(group_cast)
    [controller] = [
        call.args[0]
        for call in group_cast.register_handler.call_args_list
        if isinstance(call.args[0], MultizoneController)
    ]
    listener = MagicMock(spec=MultiZoneManagerListener)
    manager.register_listener(MEMBER_UUID, listener)

    controller.receive_message(
        MagicMock(),
        {
            "type": "DEVICE_ADDED",
            "requestId": 0,
            "device": {"deviceId": str(MEMBER_UUID), "name": "Korridor"},
        },
    )

    listener.added_to_multizone.assert_called_once_with(str(GROUP_UUID))
    listener.multizone_new_cast_status.assert_called_once_with(
        str(GROUP_UUID), group_cast.status
    )
    listener.multizone_new_media_status.assert_called_once_with(
        str(GROUP_UUID), group_cast.media_controller.status
    )
    assert manager.get_multizone_memberships(MEMBER_UUID) == [str(GROUP_UUID)]
