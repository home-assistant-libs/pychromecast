"""Tests for the socket client."""

import socket
import threading
from collections.abc import Generator
from struct import pack, unpack
from unittest.mock import MagicMock, Mock

import pytest

from pychromecast.generated.cast_channel_pb2 import (  # pylint: disable=no-name-in-module
    CastMessage,
)
from pychromecast.error import NotConnected, PyChromecastStopped
from pychromecast.socket_client import NS_CONNECTION, SocketClient


def _lock_held(client: SocketClient) -> bool:
    """Return True if the socket lock is held, by any thread."""
    lock = getattr(client, "_socket_lock", None)
    if lock is None:
        return False
    acquired: list[bool] = []

    def try_acquire() -> None:
        acquired.append(lock.acquire(blocking=False))
        if acquired[0]:
            lock.release()

    thread = threading.Thread(target=try_acquire)
    thread.start()
    thread.join()
    return not acquired[0]


def _frame(msg: CastMessage) -> bytes:
    payload = msg.SerializeToString()
    return pack(">I", len(payload)) + payload


class FakeSocket:
    """Socket recording messages and whether the socket lock was held."""

    def __init__(
        self, client: SocketClient, data: bytes = b"", error: OSError | None = None
    ) -> None:
        self._client = client
        self._data = data
        self._error = error
        self.locked: list[bool] = []
        self.sent: list[CastMessage] = []

    def sendall(self, data: bytes) -> None:
        """Record a written message."""
        self.locked.append(_lock_held(self._client))
        if self._error:
            raise self._error
        (length,) = unpack(">I", data[:4])
        msg = CastMessage()
        msg.ParseFromString(data[4 : 4 + length])
        self.sent.append(msg)

    def recv(self, bufsize: int) -> bytes:
        """Return queued data."""
        self.locked.append(_lock_held(self._client))
        chunk, self._data = self._data[:bufsize], self._data[bufsize:]
        return chunk


@pytest.fixture(name="client")
def client_fixture() -> Generator[SocketClient]:
    """Return a socket client which is not connected."""
    client = SocketClient(
        cast_type="cast",
        tries=1,
        timeout=1,
        retry_wait=1,
        services=set(),
        zconf=None,
    )
    client.connecting = False
    yield client
    client.socketpair[0].close()
    client.socketpair[1].close()
    client.selector.close()


def test_send_holds_socket_lock(client: SocketClient) -> None:
    """Test sends hold the socket lock, an SSLSocket is not thread safe."""
    sock = FakeSocket(client)
    client.socket = sock  # type: ignore[assignment]

    client.send_message("receiver-0", "urn:x-cast:test", {"type": "TEST"})

    # The channel CONNECT message and the message itself
    assert sock.locked == [True, True]


def test_read_holds_socket_lock(client: SocketClient) -> None:
    """Test reads hold the socket lock, an SSLSocket is not thread safe."""
    msg = CastMessage(
        protocol_version=CastMessage.CASTV2_1_0,
        source_id="receiver-0",
        destination_id="sender-0",
        namespace="urn:x-cast:test",
        payload_type=CastMessage.STRING,
        payload_utf8="{}",
    )
    sock = FakeSocket(client, _frame(msg))
    client.socket = sock  # type: ignore[assignment]

    assert client._read_message() == msg  # pylint: disable=protected-access
    assert sock.locked and all(sock.locked)


def test_cleanup_closes_all_channels(client: SocketClient) -> None:
    """Test all channels are closed, also when there are several."""
    sock = FakeSocket(client)
    client.socket = sock  # type: ignore[assignment]
    client.send_message("receiver-0", "urn:x-cast:test", {"type": "TEST"})
    client.send_message("app-1", "urn:x-cast:test", {"type": "TEST"})
    client.send_message("app-2", "urn:x-cast:test", {"type": "TEST"})
    sock.sent.clear()

    client._cleanup()  # pylint: disable=protected-access

    assert [
        (msg.destination_id, msg.namespace, msg.payload_utf8) for msg in sock.sent
    ] == [
        (dest, NS_CONNECTION, '{"type": "CLOSE", "origin": {}}')
        for dest in ("receiver-0", "app-1", "app-2")
    ]
    assert not client._open_channels  # pylint: disable=protected-access


def _callback(client: SocketClient) -> tuple[MagicMock, list[bool]]:
    """Return a callback recording whether the socket lock was held."""
    locked: list[bool] = []
    callback = MagicMock(side_effect=lambda *_: locked.append(_lock_held(client)))
    return callback, locked


def test_callback_without_request_id_runs_unlocked(client: SocketClient) -> None:
    """Test the callback of a message without request id runs without the lock."""
    client.socket = FakeSocket(client)  # type: ignore[assignment]
    callback, locked = _callback(client)

    client.send_message(
        "receiver-0",
        "urn:x-cast:test",
        {"type": "TEST"},
        callback_function=callback,
        no_add_request_id=True,
    )

    callback.assert_called_once_with(True, None)
    assert locked == [False]


def test_callback_not_connected_runs_unlocked(client: SocketClient) -> None:
    """Test the callback is failed without the lock when not connected."""
    client.socket = FakeSocket(client)  # type: ignore[assignment]
    client.connecting = True
    callback, locked = _callback(client)

    with pytest.raises(NotConnected):
        client.send_message(
            "receiver-0", "urn:x-cast:test", {}, callback_function=callback
        )

    callback.assert_called_once_with(False, None)
    assert locked == [False]


def test_callback_write_error_runs_unlocked(client: SocketClient) -> None:
    """Test the callback is failed without the lock when writing fails."""
    client.socket = FakeSocket(  # type: ignore[assignment]
        client, error=socket.error("broken")
    )
    client._open_channels.append("receiver-0")  # pylint: disable=protected-access
    callback, locked = _callback(client)

    client.send_message("receiver-0", "urn:x-cast:test", {}, callback_function=callback)

    callback.assert_called_once_with(False, None)
    assert locked == [False]
    assert not client._request_callbacks  # pylint: disable=protected-access
    assert client._force_recon  # pylint: disable=protected-access


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
