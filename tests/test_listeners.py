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


def test_unregister_status_listener_while_notified() -> None:
    """Test a listener unregistering itself doesn't hide the status from others."""
    controller = ReceiverController()
    first = MagicMock()
    second = MagicMock()
    first.new_cast_status.side_effect = lambda status: unregister()
    unregister = controller.register_status_listener(first)
    controller.register_status_listener(second)

    controller._process_get_status(STATUS)  # pylint: disable=protected-access

    first.new_cast_status.assert_called_once()
    second.new_cast_status.assert_called_once()


def test_unregister_keeps_later_registration() -> None:
    """Test an old unregister function doesn't remove a new registration."""
    controller = ReceiverController()
    listener = MagicMock()
    unregister = controller.register_status_listener(listener)
    unregister()
    controller.register_status_listener(listener)

    unregister()
    controller._process_get_status(STATUS)  # pylint: disable=protected-access

    listener.new_cast_status.assert_called_once()


def test_unregister_equal_listener() -> None:
    """Test unregistering removes the registered listener, not an equal one."""
    controller = ReceiverController()
    first = MagicMock()
    second = MagicMock()
    first.__eq__ = second.__eq__ = lambda self, other: True
    controller.register_status_listener(first)
    unregister = controller.register_status_listener(second)

    unregister()
    controller._process_get_status(STATUS)  # pylint: disable=protected-access

    first.new_cast_status.assert_called_once()
    second.new_cast_status.assert_not_called()
