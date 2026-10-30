"""Tests for pychromecast.controllers.receiver."""

from collections.abc import Generator
import json
import logging

import pytest

from pychromecast.controllers.receiver import NS_RECEIVER, ReceiverController
from pychromecast.generated.cast_channel_pb2 import (  # pylint: disable=no-name-in-module
    CastMessage,
)
from pychromecast.socket_client import SocketClient

APP_AVAILABILITY = {
    "availability": {"CC1AD845": "APP_AVAILABLE", "233637DE": "APP_UNAVAILABLE"},
    "requestId": 7,
    "responseType": "GET_APP_AVAILABILITY",
}


@pytest.fixture(name="socket_client")
def socket_client_fixture() -> Generator[SocketClient]:
    """Return a socket client which is not connected."""
    client = SocketClient(
        cast_type="cast",
        tries=1,
        timeout=10,
        retry_wait=0.01,
        services=set(),
        zconf=None,
    )
    yield client
    for sock in client.socketpair:
        sock.close()
    client.selector.close()


def _message(data: dict) -> CastMessage:
    return CastMessage(
        protocol_version=CastMessage.CASTV2_1_0,
        source_id="receiver-0",
        destination_id="sender-0",
        namespace=NS_RECEIVER,
        payload_type=CastMessage.STRING,
        payload_utf8=json.dumps(data),
    )


def test_response_without_type_is_not_handled() -> None:
    """Test a reply with a responseType but no type is left unhandled."""
    controller = ReceiverController()

    assert not controller.receive_message(_message(APP_AVAILABILITY), APP_AVAILABILITY)
    assert controller.status is None


def test_response_without_type_is_routed(
    socket_client: SocketClient, caplog: pytest.LogCaptureFixture
) -> None:
    """Test a reply with a responseType but no type is routed without errors."""
    with caplog.at_level(logging.DEBUG, logger="pychromecast"):
        socket_client._route_message(  # pylint: disable=protected-access
            _message(APP_AVAILABILITY), APP_AVAILABILITY
        )

    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]
