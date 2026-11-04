"""Tests for the base controller."""

from unittest.mock import MagicMock

import pytest

from pychromecast.controllers import BaseController
from pychromecast.error import ControllerNotRegistered


def test_send_message_after_unregistered() -> None:
    """Test a message sent by an unregistered controller raises."""
    controller = BaseController("urn:x-cast:test", target_platform=True)
    controller.registered(MagicMock())
    controller.unregistered()

    with pytest.raises(ControllerNotRegistered):
        controller.send_message({"type": "TEST"})


def test_send_message_nocheck_after_unregistered() -> None:
    """Test a message sent unchecked by an unregistered controller raises."""
    controller = BaseController("urn:x-cast:test", target_platform=True)
    controller.registered(MagicMock())
    controller.unregistered()
    callback = MagicMock()

    with pytest.raises(ControllerNotRegistered):
        controller.send_message_nocheck({"type": "TEST"}, callback_function=callback)
    callback.assert_called_once_with(False, None)
