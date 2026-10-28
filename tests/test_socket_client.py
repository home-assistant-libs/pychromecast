"""Tests for pychromecast.socket_client."""

from collections.abc import Generator
import logging
import socket
import ssl
from unittest.mock import MagicMock, Mock, PropertyMock, patch

import pytest

from pychromecast.error import ChromecastConnectionError, PyChromecastStopped
from pychromecast.models import HostServiceInfo
from pychromecast.socket_client import SocketClient, _SocketClientLogger


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


@pytest.mark.parametrize(
    ("fn", "host", "prefix"),
    [
        ("Kitchen", "192.0.2.1", "[Kitchen(192.0.2.1):8009]"),
        ("100% Speaker", "192.0.2.1", "[100% Speaker(192.0.2.1):8009]"),
        ("Kitchen", "fe80::1%2", "[Kitchen(fe80::1%2):8009]"),
        ("%s %d", "fe80::1%eth0", "[%s %d(fe80::1%eth0):8009]"),
        (None, "192.0.2.1", "[(192.0.2.1):8009]"),
    ],
)
def test_log_prefix_with_percent(
    caplog: pytest.LogCaptureFixture, fn: str | None, host: str, prefix: str
) -> None:
    """Test the prefix and message may contain %, with and without arguments.

    Positional and mapping arguments are both supported.
    """
    client = Mock(fn=fn, host=host, port=8009)
    logger = _SocketClientLogger(
        logging.getLogger("pychromecast.socket_client"), client
    )

    with caplog.at_level(logging.DEBUG, logger="pychromecast.socket_client"):
        logger.debug("Connected!")
        logger.debug("Volume 100%")
        logger.debug("Volume %d%% %s", 50, "100%")
        logger.info("Received: %s", "%s %d")
        logger.debug("Volume %(volume)d%%", {"volume": 50})
        logger.debug("State %(state)s", {"state": "100%"})

    assert caplog.messages == [
        f"{prefix} Connected!",
        f"{prefix} Volume 100%",
        f"{prefix} Volume 50% 100%",
        f"{prefix} Received: %s %d",
        f"{prefix} Volume 50%",
        f"{prefix} State 100%",
    ]
    # The args are kept, formatting is left to logging
    assert [record.args for record in caplog.records] == [
        (),
        (),
        (50, "100%"),
        ("%s %d",),
        {"volume": 50},
        {"state": "100%"},
    ]
    assert all(record.exc_info is None for record in caplog.records)
    # The records name the caller, not the adapter
    assert {record.funcName for record in caplog.records} == {
        "test_log_prefix_with_percent"
    }


def test_log_stacklevel(caplog: pytest.LogCaptureFixture) -> None:
    """Test a stacklevel passed by the caller is honored."""
    client = Mock(fn="100% Speaker", host="fe80::1%2", port=8009)
    logger = _SocketClientLogger(
        logging.getLogger("pychromecast.socket_client"), client
    )

    def log_helper() -> None:
        logger.debug("Volume %s", "100%", stacklevel=2)

    with caplog.at_level(logging.DEBUG, logger="pychromecast.socket_client"):
        log_helper()

    assert caplog.messages == ["[100% Speaker(fe80::1%2):8009] Volume 100%"]
    assert caplog.records[0].funcName == "test_log_stacklevel"


def test_log_exception_with_percent(caplog: pytest.LogCaptureFixture) -> None:
    """Test exception logging with % in the prefix and message."""
    client = Mock(fn="100% Speaker", host="fe80::1%2", port=8009)
    logger = _SocketClientLogger(
        logging.getLogger("pychromecast.socket_client"), client
    )

    with caplog.at_level(logging.DEBUG, logger="pychromecast.socket_client"):
        try:
            raise ValueError("boom")
        except ValueError:
            logger.exception("Failed at 100%")

    assert caplog.messages == ["[100% Speaker(fe80::1%2):8009] Failed at 100%"]
    assert caplog.records[0].exc_info[0] is ValueError


def test_log_disabled_level_is_skipped(caplog: pytest.LogCaptureFixture) -> None:
    """Test nothing is logged, or prefixed, below the logger level."""
    client = Mock(host="fe80::1%2", port=8009)
    # The prefix must not be built for a disabled level
    type(client).fn = PropertyMock(side_effect=AssertionError("prefix built"))
    logger = _SocketClientLogger(
        logging.getLogger("pychromecast.socket_client"), client
    )

    with caplog.at_level(logging.INFO, logger="pychromecast.socket_client"):
        logger.debug("Volume %s", "100%")

    assert caplog.records == []
