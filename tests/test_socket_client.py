"""Tests for SocketClient shutdown handling."""

from unittest.mock import Mock

import pytest

from pychromecast.error import NotConnected, PyChromecastStopped
from pychromecast.socket_client import SocketClient


def test_stopped_during_worker_does_not_log_exception() -> None:
    """An expected shutdown must not be logged as a worker failure."""
    client = object.__new__(SocketClient)

    client.fn = "Test Chromecast"
    client.host = "192.0.2.1"
    client.port = 8009

    client.stop = Mock()
    client.stop.is_set.side_effect = [False, True, True]
    client._run_once = Mock(
        side_effect=PyChromecastStopped("Socket client's thread is stopped.")
    )
    client.initialize_connection = Mock()
    client.heartbeat_controller = Mock()
    client.logger = Mock()
    client._cleanup = Mock()
    client._force_recon = False

    client.run()

    client._run_once.assert_called_once()
    client.logger.exception.assert_not_called()
    assert client._force_recon is False
    client._cleanup.assert_called_once()


def test_stopped_exception_exits_worker() -> None:
    """A stopped socket client exits the worker loop cleanly."""
    client = object.__new__(SocketClient)

    client.fn = "Test Chromecast"
    client.host = "192.0.2.1"
    client.port = 8009

    client.stop = Mock()
    client.stop.is_set.side_effect = [False, False]
    client._run_once = Mock(
        side_effect=PyChromecastStopped("Socket client's thread is stopped.")
    )
    client.initialize_connection = Mock()
    client.heartbeat_controller = Mock()
    client.logger = Mock()
    client._cleanup = Mock()
    client._force_recon = False

    client.run()

    client._run_once.assert_called_once()
    client.logger.exception.assert_not_called()
    assert client._force_recon is False
    client._cleanup.assert_called_once()


def test_send_message_on_torn_down_socket_raises_not_connected() -> None:
    """A send racing socket teardown raises NotConnected instead of crashing."""
    client = SocketClient(
        cast_type="audio",
        tries=1,
        timeout=1,
        retry_wait=1,
        services=set(),
        zconf=None,
    )
    try:
        client.connecting = False
        client.socket = None

        with pytest.raises(NotConnected):
            client.send_message(
                "receiver-0",
                "urn:x-cast:com.google.cast.receiver",
                {"type": "STOP"},
            )
    finally:
        client.socketpair[0].close()
        client.socketpair[1].close()
        client.selector.close()
