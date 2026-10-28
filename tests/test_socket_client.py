"""Tests for SocketClient shutdown handling."""

import logging
from unittest.mock import Mock

import pytest

from pychromecast.error import PyChromecastStopped
from pychromecast.socket_client import SocketClient, _SocketClientLogger


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
    ],
)
def test_log_prefix_with_percent(
    caplog: pytest.LogCaptureFixture, fn: str, host: str, prefix: str
) -> None:
    """Test the prefix and message may contain %, with and without arguments."""
    client = Mock(fn=fn, host=host, port=8009)
    logger = _SocketClientLogger(
        logging.getLogger("pychromecast.socket_client"), client
    )

    with caplog.at_level(logging.DEBUG, logger="pychromecast.socket_client"):
        logger.debug("Connected!")
        logger.debug("Volume 100%")
        logger.debug("Volume %d%% %s", 50, "100%")
        logger.info("Received: %s", "%s %d")

    assert caplog.messages == [
        f"{prefix} Connected!",
        f"{prefix} Volume 100%",
        f"{prefix} Volume 50% 100%",
        f"{prefix} Received: %s %d",
    ]
    # The records name the caller, not the adapter
    assert {record.funcName for record in caplog.records} == {
        "test_log_prefix_with_percent"
    }


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
    assert caplog.records[0].exc_info is not None


def test_log_disabled_level_is_skipped(caplog: pytest.LogCaptureFixture) -> None:
    """Test nothing is logged below the logger level."""
    client = Mock(fn="100% Speaker", host="fe80::1%2", port=8009)
    logger = _SocketClientLogger(
        logging.getLogger("pychromecast.socket_client"), client
    )

    with caplog.at_level(logging.INFO, logger="pychromecast.socket_client"):
        logger.debug("Volume %s", "100%")

    assert caplog.records == []
