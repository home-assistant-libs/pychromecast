"""Tests for pychromecast.controllers.setup."""

from collections.abc import Callable
import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from pychromecast.controllers.setup import NS_SETUP, SetupController
from pychromecast.error import RequestFailed, RequestTimeout
from pychromecast.generated.cast_channel_pb2 import (  # pylint: disable=no-name-in-module
    CastMessage,
)
from pychromecast.socket_client import (
    CONNECTION_STATUS_CONNECTED,
    CONNECTION_STATUS_LOST,
    ConnectionStatus,
    NetworkAddress,
)

EUREKA_INFO = {"device_info": {"manufacturer": "Google Inc."}, "name": "Speaker"}


def _reply(data: Any = None, request_id: Any = 1, code: int = 200) -> dict:
    return {
        "type": "eureka_info",
        "request_id": request_id,
        "response_code": code,
        "response_string": "OK" if code == 200 else "Error",
        "data": EUREKA_INFO if data is None else data,
    }


def _message(data: dict) -> CastMessage:
    return CastMessage(
        protocol_version=CastMessage.CASTV2_1_0,
        source_id="receiver-0",
        destination_id="sender-0",
        namespace=NS_SETUP,
        payload_type=CastMessage.STRING,
        payload_utf8=json.dumps(data),
    )


def _receive(controller: SetupController, data: dict) -> bool:
    return controller.receive_message(_message(data), data)


def _replying(controller: SetupController, reply: dict) -> Callable[..., None]:
    """Return a send function on which the device replies at once."""

    def send(*_args: Any, **_kwargs: Any) -> None:
        _receive(controller, reply)

    return send


@pytest.fixture(name="socket_client")
def socket_client_fixture() -> MagicMock:
    """Return a socket client which accepts all messages."""
    return MagicMock()


@pytest.fixture(name="controller")
def controller_fixture(socket_client: MagicMock) -> SetupController:
    """Return a setup controller registered with the socket client."""
    controller = SetupController()
    controller.registered(socket_client)
    return controller


def test_request_eureka_info(
    controller: SetupController, socket_client: MagicMock
) -> None:
    """Test that eureka_info is requested with request_id and the reply passed on."""
    callback = MagicMock()
    controller.request_eureka_info(["device_info", "name"], callback_function=callback)

    args, kwargs = socket_client.send_platform_message.call_args
    assert args == (
        NS_SETUP,
        {
            "type": "eureka_info",
            "request_id": 1,
            "data": {"params": ["device_info", "name"]},
        },
    )
    assert kwargs["no_add_request_id"]
    kwargs["callback_function"](True, None)
    callback.assert_not_called()

    assert _receive(controller, _reply())
    callback.assert_called_once_with(True, _reply())
    assert not _receive(controller, _reply())


@pytest.mark.parametrize(
    "data",
    [
        {"type": "other", "request_id": 1},
        _reply(request_id=2),
        _reply(request_id="1"),
        _reply(request_id=[1]),
    ],
)
def test_other_messages_not_handled(controller: SetupController, data: dict) -> None:
    """Test that other messages and replies to other requests are left unhandled."""
    callback = MagicMock()
    controller.request_eureka_info(["name"], callback_function=callback)

    assert not _receive(controller, data)
    callback.assert_not_called()


@pytest.mark.parametrize("reply", [_reply(code=404), _reply(data=["not", "a", "dict"])])
def test_failed_reply(controller: SetupController, reply: dict) -> None:
    """Test that an error reply or one without data fails the request."""
    callback = MagicMock()
    controller.request_eureka_info(["name"], callback_function=callback)

    assert _receive(controller, reply)
    callback.assert_called_once_with(False, reply)


def test_not_sent(controller: SetupController, socket_client: MagicMock) -> None:
    """Test that a request which wasn't sent fails, also if a reply arrives."""
    callback = MagicMock()
    controller.request_eureka_info(["name"], callback_function=callback)

    socket_client.send_platform_message.call_args[1]["callback_function"](False, None)
    callback.assert_called_once_with(False, None)
    assert not _receive(controller, _reply())


def test_connection_lost(controller: SetupController, socket_client: MagicMock) -> None:
    """Test that pending requests fail when the connection is lost."""
    callback = MagicMock()
    controller.request_eureka_info(["name"], callback_function=callback)
    address = NetworkAddress("192.0.2.1", 8009)

    socket_client.register_connection_listener.assert_called_once_with(controller)
    controller.new_connection_status(
        ConnectionStatus(CONNECTION_STATUS_CONNECTED, address, None)
    )
    callback.assert_not_called()
    controller.new_connection_status(
        ConnectionStatus(CONNECTION_STATUS_LOST, address, None)
    )
    callback.assert_called_once_with(False, None)
    assert not _receive(controller, _reply())


def test_tear_down(controller: SetupController, socket_client: MagicMock) -> None:
    """Test that pending requests fail and the listener is removed on tear down."""
    callback = MagicMock()
    controller.request_eureka_info(["name"], callback_function=callback)

    controller.tear_down()
    callback.assert_called_once_with(False, None)
    socket_client.register_connection_listener.return_value.assert_called_once_with()


def test_get_eureka_info(controller: SetupController, socket_client: MagicMock) -> None:
    """Test that get_eureka_info returns the data of the reply."""
    socket_client.send_platform_message.side_effect = _replying(controller, _reply())
    assert controller.get_eureka_info(["name"]) == EUREKA_INFO


def test_get_eureka_info_failed(
    controller: SetupController, socket_client: MagicMock
) -> None:
    """Test that get_eureka_info raises if the request fails."""
    socket_client.send_platform_message.side_effect = _replying(
        controller, _reply(code=404)
    )
    with pytest.raises(RequestFailed):
        controller.get_eureka_info(["name"])


def test_get_eureka_info_timeout(controller: SetupController) -> None:
    """Test that get_eureka_info raises if no reply arrives."""
    with pytest.raises(RequestTimeout):
        controller.get_eureka_info(["name"], timeout=0.01)
