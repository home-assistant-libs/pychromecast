"""Tests for pychromecast.socket_client."""

from collections.abc import Generator
import logging
import selectors
import socket
import ssl
from struct import pack, unpack
import threading
from unittest.mock import MagicMock, Mock, PropertyMock, patch

import pytest

from pychromecast.error import (
    ChromecastConnectionClosed,
    ChromecastConnectionError,
    NotConnected,
    PyChromecastStopped,
)
from pychromecast.generated.cast_channel_pb2 import (  # pylint: disable=no-name-in-module
    CastMessage,
)
from pychromecast.models import HostServiceInfo
from pychromecast.socket_client import NS_CONNECTION, SocketClient, _SocketClientLogger


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


def _message(payload: str = "{}") -> CastMessage:
    return CastMessage(
        protocol_version=CastMessage.CASTV2_1_0,
        source_id="receiver-0",
        destination_id="sender-0",
        namespace="urn:x-cast:test",
        payload_type=CastMessage.STRING,
        payload_utf8=payload,
    )


def _frame(msg: CastMessage) -> bytes:
    payload = msg.SerializeToString()
    return pack(">I", len(payload)) + payload


class FakeSocket:
    """Socket recording messages and whether the socket lock was held."""

    def __init__(
        self, client: SocketClient, data: bytes = b"", error: OSError | None = None
    ) -> None:
        self._client = client
        # Each item is a TLS record or an error, then it would block
        self.reads: list[bytes | ssl.SSLError] = [data] if data else []
        self._error = error
        self.locked: list[bool] = []
        self.sent: list[CastMessage] = []
        self.timeout: float | None = None
        self._pending = 0
        # Gives the selector something to watch
        self._pair = socket.socketpair()
        # Connected like initialize_connection would
        client.socket = self  # type: ignore[assignment]
        client.remote_selector_key = client.selector.register(
            self, selectors.EVENT_READ
        )
        client.connecting = False

    def fileno(self) -> int:
        """Return a file descriptor for the selector."""
        return self._pair[0].fileno()

    def close(self) -> None:
        """Close the file descriptor of the selector."""
        self._pair[0].close()
        self._pair[1].close()

    def settimeout(self, timeout: float | None) -> None:
        """Record the timeout."""
        self.timeout = timeout

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
        """Return data from one record, like a non-blocking SSLSocket."""
        self.locked.append(_lock_held(self._client))
        assert self.timeout == 0, "recv would block"
        if not self.reads:
            raise ssl.SSLWantReadError
        record = self.reads.pop(0)
        if isinstance(record, ssl.SSLError):
            raise record
        chunk, rest = record[:bufsize], record[bufsize:]
        if rest:
            self.reads.insert(0, rest)
        self._pending = len(rest)
        return chunk

    def pending(self) -> int:
        """Return the decrypted data left of the current record."""
        self.locked.append(_lock_held(self._client))
        return self._pending


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


def test_send_holds_socket_lock(socket_client: SocketClient) -> None:
    """Test sends hold the socket lock, an SSLSocket is not thread safe."""
    sock = FakeSocket(socket_client)

    socket_client.send_message("receiver-0", "urn:x-cast:test", {"type": "TEST"})

    # The channel CONNECT message and the message itself
    assert sock.locked == [True, True]


def test_read_holds_socket_lock(socket_client: SocketClient) -> None:
    """Test reads hold the socket lock, an SSLSocket is not thread safe."""
    msg = _message()
    sock = FakeSocket(socket_client, _frame(msg))

    assert socket_client._read_messages() == [msg]  # pylint: disable=protected-access
    assert sock.locked and all(sock.locked)
    # The timeout is restored for senders
    assert sock.timeout == socket_client.timeout


def test_read_partial_message(socket_client: SocketClient) -> None:
    """Test a partial message is kept until the rest of it is received."""
    msg = _message('{"type": "TEST"}')
    frame = _frame(msg)
    sock = FakeSocket(socket_client)

    # Only part of the length prefix
    sock.reads = [frame[:2]]
    assert not socket_client._read_messages()  # pylint: disable=protected-access
    # The length prefix and part of the payload
    sock.reads = [frame[2:10]]
    assert not socket_client._read_messages()  # pylint: disable=protected-access
    # The rest of the message, split over two records
    sock.reads = [frame[10:15], frame[15:]]
    assert not socket_client._read_messages()  # pylint: disable=protected-access
    assert socket_client._read_messages() == [msg]  # pylint: disable=protected-access


def test_read_several_messages(socket_client: SocketClient) -> None:
    """Test all complete messages are returned when several are received."""
    msgs = [_message(f'{{"n": {n}}}') for n in range(3)]
    data = b"".join(_frame(msg) for msg in msgs)
    sock = FakeSocket(socket_client)

    # Two and a half messages, then the rest
    sock.reads = [data[:-3]]
    assert socket_client._read_messages() == msgs[:2]  # pylint: disable=protected-access
    sock.reads = [data[-3:]]
    assert socket_client._read_messages() == msgs[2:]  # pylint: disable=protected-access


def test_read_one_record(socket_client: SocketClient) -> None:
    """Test one record is read at a time, so data never stops the reader."""
    msgs = [_message(f'{{"n": {n}}}') for n in range(2)]
    sock = FakeSocket(socket_client)
    sock.reads = [_frame(msg) for msg in msgs]

    assert socket_client._read_messages() == msgs[:1]  # pylint: disable=protected-access
    assert socket_client._read_messages() == msgs[1:]  # pylint: disable=protected-access


def test_read_pending_data(socket_client: SocketClient) -> None:
    """Test decrypted data left in the SSL buffer is read."""
    # A record larger than a recv
    msg = _message(f'{{"data": "{"x" * 70000}"}}')
    sock = FakeSocket(socket_client)
    sock.reads = [_frame(msg)]

    assert socket_client._read_messages() == [msg]  # pylint: disable=protected-access
    assert not sock.reads


def test_read_message_before_connection_closed(socket_client: SocketClient) -> None:
    """Test a message received just before the connection closes is returned."""
    msg = _message()
    sock = FakeSocket(socket_client)
    sock.reads = [_frame(msg), b""]

    assert socket_client._read_messages() == [msg]  # pylint: disable=protected-access
    with pytest.raises(ChromecastConnectionClosed):
        socket_client._read_messages()  # pylint: disable=protected-access


def test_read_retried_when_writable(socket_client: SocketClient) -> None:
    """Test a read waiting for TLS to write is retried when it can write."""
    msg = _message()
    sock = FakeSocket(socket_client)
    sock.reads = [ssl.SSLWantWriteError(), _frame(msg)]

    assert not socket_client._read_messages()  # pylint: disable=protected-access
    assert socket_client.remote_selector_key is not None
    # Only waiting for writes, a readable socket would wake the selector again
    assert socket_client.remote_selector_key.events == selectors.EVENT_WRITE
    # A writable socket wakes the selector like a readable one
    assert socket_client.remote_selector_key in {
        key for key, _ in socket_client.selector.select(0)
    }

    assert socket_client._read_messages() == [msg]  # pylint: disable=protected-access
    assert socket_client.remote_selector_key.events == selectors.EVENT_READ


def test_read_connection_closed(socket_client: SocketClient) -> None:
    """Test a closed connection is detected and the timeout restored."""
    sock = FakeSocket(socket_client)
    sock.reads = [b""]

    with pytest.raises(ChromecastConnectionClosed):
        socket_client._read_messages()  # pylint: disable=protected-access
    assert sock.timeout == socket_client.timeout


def test_channel_not_open_when_connecting(socket_client: SocketClient) -> None:
    """Test a channel is not marked open when its CONNECT can't be sent.

    A request callback failed by a reconnect may retry its send, the channel
    must then be connected on the new connection.
    """
    sock = FakeSocket(socket_client)
    socket_client.connecting = True

    with pytest.raises(NotConnected):
        socket_client.send_message("receiver-0", "urn:x-cast:test", {"type": "TEST"})
    assert not socket_client._open_channels  # pylint: disable=protected-access

    socket_client.connecting = False
    socket_client.send_message("receiver-0", "urn:x-cast:test", {"type": "TEST"})
    assert [msg.namespace for msg in sock.sent] == [NS_CONNECTION, "urn:x-cast:test"]


def test_cleanup_closes_all_channels(socket_client: SocketClient) -> None:
    """Test all channels are closed, also when there are several."""
    sock = FakeSocket(socket_client)
    socket_client.send_message("receiver-0", "urn:x-cast:test", {"type": "TEST"})
    socket_client.send_message("app-1", "urn:x-cast:test", {"type": "TEST"})
    socket_client.send_message("app-2", "urn:x-cast:test", {"type": "TEST"})
    sock.sent.clear()

    socket_client._cleanup()  # pylint: disable=protected-access

    assert [
        (msg.destination_id, msg.namespace, msg.payload_utf8) for msg in sock.sent
    ] == [
        (dest, NS_CONNECTION, '{"type": "CLOSE", "origin": {}}')
        for dest in ("receiver-0", "app-1", "app-2")
    ]
    assert not socket_client._open_channels  # pylint: disable=protected-access


def test_disconnect_channel_removed_while_waiting(socket_client: SocketClient) -> None:
    """Test a channel removed by a sender while reconnecting is skipped.

    A sender rolls back a channel when its CONNECT can't be sent.
    """
    FakeSocket(socket_client)
    socket_client.send_message("receiver-0", "urn:x-cast:test", {"type": "TEST"})
    # Reconnecting, sends fail
    socket_client.connecting = True
    errors: list[Exception] = []

    def disconnect() -> None:
        try:
            socket_client.disconnect_channel("receiver-0")
        except Exception as err:  # pylint: disable=broad-except
            errors.append(err)

    with socket_client._socket_lock:  # pylint: disable=protected-access
        thread = threading.Thread(target=disconnect)
        thread.start()
        # The disconnect waits for the lock
        thread.join(0.1)
        socket_client._open_channels.remove("receiver-0")  # pylint: disable=protected-access
    thread.join()

    assert not errors


def _callback(client: SocketClient) -> tuple[MagicMock, list[bool]]:
    """Return a callback recording whether the socket lock was held."""
    locked: list[bool] = []
    callback = MagicMock(side_effect=lambda *_: locked.append(_lock_held(client)))
    return callback, locked


def test_callback_without_request_id_runs_unlocked(socket_client: SocketClient) -> None:
    """Test the callback of a message without request id runs without the lock."""
    FakeSocket(socket_client)
    callback, locked = _callback(socket_client)

    socket_client.send_message(
        "receiver-0",
        "urn:x-cast:test",
        {"type": "TEST"},
        callback_function=callback,
        no_add_request_id=True,
    )

    callback.assert_called_once_with(True, None)
    assert locked == [False]


def test_callback_not_connected_runs_unlocked(socket_client: SocketClient) -> None:
    """Test the callback is failed without the lock when not connected."""
    FakeSocket(socket_client)
    socket_client.connecting = True
    callback, locked = _callback(socket_client)

    with pytest.raises(NotConnected):
        socket_client.send_message(
            "receiver-0", "urn:x-cast:test", {}, callback_function=callback
        )

    callback.assert_called_once_with(False, None)
    assert locked == [False]


def test_callback_write_error_runs_unlocked(socket_client: SocketClient) -> None:
    """Test the callback is failed without the lock when writing fails."""
    FakeSocket(socket_client, error=socket.error("broken"))
    socket_client._open_channels.append("receiver-0")  # pylint: disable=protected-access
    callback, locked = _callback(socket_client)

    socket_client.send_message(
        "receiver-0", "urn:x-cast:test", {}, callback_function=callback
    )

    callback.assert_called_once_with(False, None)
    assert locked == [False]
    assert not socket_client._request_callbacks  # pylint: disable=protected-access
    assert socket_client._force_recon  # pylint: disable=protected-access


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
