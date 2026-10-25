"""Tests for registering and unregistering listeners."""

from unittest.mock import MagicMock

from pychromecast.controllers.receiver import ReceiverController

STATUS = {"status": {"volume": {"level": 0.5, "muted": False}}}


def test_unregister_status_listener() -> None:
    """Test an unregistered listener is no longer called."""
    controller = ReceiverController()
    listener = MagicMock()
    unregister = controller.register_status_listener(listener)

    controller._process_get_status(STATUS)  # pylint: disable=protected-access
    assert listener.new_cast_status.call_count == 1

    unregister()
    controller._process_get_status(STATUS)  # pylint: disable=protected-access
    assert listener.new_cast_status.call_count == 1

    # Unregistering again does nothing
    unregister()
