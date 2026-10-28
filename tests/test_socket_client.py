"""Tests for pychromecast.socket_client."""

from collections.abc import Generator
import socket
import ssl
from unittest.mock import MagicMock, Mock, patch

import pytest

from pychromecast.error import ChromecastConnectionError, PyChromecastStopped
from pychromecast.models import HostServiceInfo
from pychromecast.socket_client import SocketClient


@pytest.fixture(name="socket_client")
def socket_client_fixture() -> Generator[SocketClient]:
    """Return a socket client for a link local IPv6 host, trying once."""
    client = SocketClient(
        cast_type="cast",
        tries=1,
        timeout=10,
        retry_wait=0.01,
        services={HostServiceInfo("fe80::1%2", 8009)},
        zconf=None,
    )
    yield client
    if client.socket is not None:
        client.socket.close()
    for sock in client.socketpair:
        sock.close()
    client.selector.close()


def test_connect_wraps_before_registering(socket_client: SocketClient) -> None:
    """Test that the TLS wrapped socket is registered with the selector."""
    raw_socket = MagicMock()
    tls_socket, peer = socket.socketpair()
    context = MagicMock()
    context.wrap_socket.return_value = tls_socket
    with (
        patch("socket.create_connection", return_value=raw_socket) as connect,
        patch("ssl.SSLContext", return_value=context),
    ):
        socket_client.initialize_connection()
    peer.close()

    connect.assert_called_once_with(("fe80::1%2", 8009), 10)
    context.wrap_socket.assert_called_once_with(raw_socket)
    assert socket_client.socket is tls_socket
    assert socket_client.remote_selector_key is not None
    assert socket_client.remote_selector_key.fileobj is tls_socket
    raw_socket.close.assert_not_called()


def test_connect_closes_raw_socket_on_failed_wrap(
    socket_client: SocketClient,
) -> None:
    """Test that the raw socket is closed and not registered if wrapping fails."""
    raw_socket = MagicMock()
    context = MagicMock()
    context.wrap_socket.side_effect = ssl.SSLError("handshake failed")
    with (
        patch("socket.create_connection", return_value=raw_socket),
        patch("ssl.SSLContext", return_value=context),
        pytest.raises(ChromecastConnectionError),
    ):
        socket_client.initialize_connection()

    raw_socket.close.assert_called_once_with()
    assert socket_client.socket is None
    assert socket_client.remote_selector_key is None


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
