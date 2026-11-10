"""Tests for device authentication in pychromecast.socket_client."""

from collections.abc import Callable, Generator
from dataclasses import replace
from datetime import timedelta
import json
import logging
from pathlib import Path
import select
import socket
import ssl
from struct import unpack
import threading
import time
from typing import Any
from unittest.mock import MagicMock, Mock, patch
from uuid import UUID

import pytest
from device_auth_helpers import (
    NOW,
    OTHER_UUID,
    TEST_UUID,
    EurekaServer,
    TestPKI,
    TLSServer,
    eureka_info,
    frame,
    group_entry,
    refused_port,
    der,
    key_usage,
    make_cert,
    make_reply,
    make_tls_cert,
    rsa_key,
)

from pychromecast.controllers.heartbeat import NS_HEARTBEAT
from pychromecast.controllers.receiver import NS_RECEIVER, CastStatus
from pychromecast.device_auth import (
    NS_DEVICE_AUTH,
    DeviceAuthFailureClass,
    DeviceAuthResult,
    DeviceAuthStatus,
)
from pychromecast.error import (
    ChromecastConnectionError,
    DeviceAuthenticationError,
    NotConnected,
)
from pychromecast.generated.cast_channel_pb2 import (  # pylint: disable=no-name-in-module
    AuthError,
    CastMessage,
    DeviceAuthMessage,
)
from pychromecast.models import HostServiceInfo
from pychromecast.socket_client import (
    CONNECTION_STATUS_CONNECTED,
    CONNECTION_STATUS_CONNECTING,
    CONNECTION_STATUS_FAILED,
    CONNECTION_STATUS_FAILED_AUTH,
    NS_CONNECTION,
    ConnectionStatus,
    ConnectionStatusListener,
    SocketClient,
)

VERIFIED = DeviceAuthResult(
    DeviceAuthStatus.VERIFIED,
    "device is genuine",
    device_cert_subject="CN=TEST",
    trust_root="Test Root CA",
    tls_cert_cn=str(TEST_UUID),
    uuid_checked=True,
    hash_algorithm="sha256",
)


def _failure(status: DeviceAuthStatus) -> DeviceAuthResult:
    return DeviceAuthResult(status, f"test {status}")


class StatusRecorder(ConnectionStatusListener):
    """Record connection statuses."""

    def __init__(self) -> None:
        self.statuses: list[ConnectionStatus] = []
        self.connected = threading.Event()

    def new_connection_status(self, status: ConnectionStatus) -> None:
        """Record a status."""
        self.statuses.append(status)
        if status.status == CONNECTION_STATUS_CONNECTED:
            self.connected.set()

    @property
    def names(self) -> list[str]:
        """Return the recorded status names."""
        return [status.status for status in self.statuses]


def _close_client(client: SocketClient) -> None:
    if client.socket is not None:
        client.socket.close()
    for sock in client.socketpair:
        sock.close()
    client.selector.close()


@pytest.fixture(name="make_client")
def make_client_fixture() -> Generator[Callable[..., SocketClient]]:
    """Return a factory of socket clients, closed after the test."""
    clients: list[SocketClient] = []

    def make(**kwargs: Any) -> SocketClient:
        options: dict[str, Any] = {
            "cast_type": "cast",
            "tries": 1,
            "timeout": 10,
            "retry_wait": 0.01,
            "services": {HostServiceInfo("192.0.2.1", 8009)},
            "zconf": None,
            "expected_uuid": TEST_UUID,
        }
        options.update(kwargs)
        client = SocketClient(**options)
        clients.append(client)
        return client

    yield make
    for client in clients:
        _close_client(client)


class FakeTLS:
    """Fake the TLS connection: each connect gets a new socket pair."""

    def __init__(self) -> None:
        self.tls_sockets: list[socket.socket] = []
        self._peers: list[socket.socket] = []
        self.context = MagicMock()
        self.context.wrap_socket.side_effect = self._wrap

    def _wrap(self, _raw: object) -> socket.socket:
        tls_socket, peer = socket.socketpair()
        self.tls_sockets.append(tls_socket)
        self._peers.append(peer)
        return tls_socket

    def close(self) -> None:
        """Close the sockets."""
        for sock in self.tls_sockets + self._peers:
            sock.close()


@pytest.fixture(name="fake_tls")
def fake_tls_fixture() -> Generator[FakeTLS]:
    """Patch connecting, return the fake TLS connections."""
    fake = FakeTLS()
    with (
        patch("socket.create_connection"),
        patch("ssl.SSLContext", return_value=fake.context),
    ):
        yield fake
    fake.close()


def test_auth_failure_does_not_connect(
    make_client: Callable[..., SocketClient], fake_tls: FakeTLS
) -> None:
    """Test nothing is sent to a device failing authentication."""
    client = make_client()
    recorder = StatusRecorder()
    client.register_connection_listener(recorder)
    wakeup = client.wakeup_selector_key
    result = _failure(DeviceAuthStatus.CHAIN_UNTRUSTED)
    with (
        patch("pychromecast.socket_client.authenticate", return_value=result),
        patch.object(client.receiver_controller, "update_status") as update_status,
        patch.object(client.heartbeat_controller, "ping") as ping,
        pytest.raises(ChromecastConnectionError, match="chain_untrusted"),
    ):
        client.initialize_connection()

    assert fake_tls.tls_sockets[0].fileno() == -1
    assert client.socket is None
    assert client.remote_selector_key is None
    assert list(client.selector.get_map().values()) == [wakeup]
    update_status.assert_not_called()
    ping.assert_not_called()
    assert recorder.names == [
        CONNECTION_STATUS_CONNECTING,
        CONNECTION_STATUS_FAILED_AUTH,
    ]
    assert recorder.statuses[1].device_auth is result
    assert client.device_auth_result is result
    assert not client.is_connected


def test_auth_runs_before_register_and_connect(
    make_client: Callable[..., SocketClient], fake_tls: FakeTLS
) -> None:
    """Test the device is authenticated before anything else."""
    client = make_client(timeout=5)
    recorder = StatusRecorder()
    client.register_connection_listener(recorder)
    manager = Mock()
    auth = Mock(return_value=VERIFIED)
    manager.attach_mock(auth, "authenticate")
    with (
        patch("pychromecast.socket_client.authenticate", auth),
        patch.object(
            client.selector, "register", wraps=client.selector.register
        ) as register,
        patch.object(client.receiver_controller, "update_status") as update_status,
        patch.object(client.heartbeat_controller, "ping"),
    ):
        manager.attach_mock(register, "register")
        manager.attach_mock(update_status, "update_status")
        client.initialize_connection()

    assert [call[0] for call in manager.mock_calls] == [
        "authenticate",
        "register",
        "update_status",
    ]
    auth.assert_called_once_with(
        fake_tls.tls_sockets[0],
        expected_uuid=TEST_UUID,
        timeout=5,
        trust_roots=None,
    )
    assert client.device_auth_result is VERIFIED
    assert client.device_auth_result.verified
    assert client.socket is fake_tls.tls_sockets[0]
    assert recorder.statuses[-1].status == CONNECTION_STATUS_CONNECTED
    assert recorder.statuses[-1].device_auth is VERIFIED
    # The socket timeout is restored
    assert fake_tls.tls_sockets[0].gettimeout() == 5


@pytest.mark.usefixtures("fake_tls")
def test_auth_timeout_capped(make_client: Callable[..., SocketClient]) -> None:
    """Test the handshake timeout is at most DEVICE_AUTH_TIMEOUT."""
    client = make_client(timeout=30)
    with (
        patch("pychromecast.socket_client.authenticate", return_value=VERIFIED) as auth,
        patch.object(client.receiver_controller, "update_status"),
        patch.object(client.heartbeat_controller, "ping"),
    ):
        client.initialize_connection()
    assert auth.call_args.kwargs["timeout"] == 10


LEADER_UUID = OTHER_UUID


def _retry_levels(caplog: pytest.LogCaptureFixture, text: str) -> list[int]:
    """Return the levels of the records containing text, and clear them."""
    levels = [
        record.levelno for record in caplog.records if text in record.getMessage()
    ]
    caplog.clear()
    return levels


def _fake_time(clock: list[float]) -> Mock:
    """Return a time module whose monotonic clock is clock[0]."""
    fake_time = Mock(wraps=time)
    fake_time.monotonic.side_effect = lambda: clock[0]
    return fake_time


@pytest.fixture(name="connect_patches")
def connect_patches_fixture() -> Generator[None]:
    """Don't talk to the device after connecting."""
    with (
        patch.object(SocketClient, "_ensure_channel_connected"),
        patch("pychromecast.controllers.receiver.ReceiverController.update_status"),
        patch("pychromecast.controllers.heartbeat.HeartbeatController.ping"),
    ):
        yield


@pytest.mark.usefixtures("connect_patches", "fake_tls")
def test_not_genuine_logging(
    make_client: Callable[..., SocketClient], caplog: pytest.LogCaptureFixture
) -> None:
    """Test a device which is not genuine is warned about once per connect."""
    client = make_client(tries=3)
    # Passing 0 to the constructor means the default
    client.retry_wait = 0
    untrusted = _failure(DeviceAuthStatus.CHAIN_UNTRUSTED)
    no_nonce = _failure(DeviceAuthStatus.NONCE_MISSING)
    text = "may not be a genuine Cast device"
    with (
        patch("pychromecast.socket_client.authenticate") as auth,
        caplog.at_level(logging.DEBUG, logger="pychromecast.socket_client"),
    ):
        auth.side_effect = [untrusted, untrusted, no_nonce]
        with pytest.raises(ChromecastConnectionError):
            client.initialize_connection()
        assert _retry_levels(caplog, text) == [
            logging.WARNING,
            logging.DEBUG,
            logging.DEBUG,
        ]

        # A new connection attempt warns again
        client.stop.clear()
        client.tries = 1
        auth.side_effect = [no_nonce]
        with pytest.raises(ChromecastConnectionError):
            client.initialize_connection()
        assert _retry_levels(caplog, text) == [logging.WARNING]


@pytest.mark.usefixtures("connect_patches", "fake_tls")
def test_clock_logging(
    make_client: Callable[..., SocketClient], caplog: pytest.LogCaptureFixture
) -> None:
    """Test certificate validity failures point at the clock and the firmware."""
    client = make_client(tries=2)
    client.retry_wait = 0
    with (
        patch(
            "pychromecast.socket_client.authenticate",
            return_value=_failure(DeviceAuthStatus.CERT_EXPIRED),
        ),
        caplog.at_level(logging.DEBUG, logger="pychromecast.socket_client"),
        pytest.raises(ChromecastConnectionError),
    ):
        client.initialize_connection()
    messages = [
        r.getMessage() for r in caplog.records if "system clock" in r.getMessage()
    ]
    assert "firmware update" in messages[0]
    assert _retry_levels(caplog, "system clock") == [logging.WARNING, logging.DEBUG]


@pytest.mark.usefixtures("connect_patches", "fake_tls")
def test_transient_logging(
    make_client: Callable[..., SocketClient], caplog: pytest.LogCaptureFixture
) -> None:
    """Test a device which doesn't reply is logged like a network failure."""
    client = make_client(tries=2)
    client.retry_wait = 0
    with (
        patch(
            "pychromecast.socket_client.authenticate",
            return_value=_failure(DeviceAuthStatus.NO_REPLY),
        ),
        caplog.at_level(logging.DEBUG, logger="pychromecast.socket_client"),
        pytest.raises(ChromecastConnectionError),
    ):
        client.initialize_connection()
    assert _retry_levels(caplog, "failed: no_reply") == [logging.INFO, logging.DEBUG]
    assert not [r for r in caplog.records if r.levelno == logging.WARNING]


def _mismatch(cn: UUID = LEADER_UUID) -> DeviceAuthResult:
    return DeviceAuthResult(
        DeviceAuthStatus.UUID_MISMATCH,
        f"TLS certificate CN {str(cn)!r} does not match",
        device_cert_subject="CN=LEADER",
        trust_root="Test Root CA",
        tls_cert_cn=str(cn),
        hash_algorithm="sha256",
        device_cert_der=b"device cert",
    )


@pytest.mark.usefixtures("connect_patches", "fake_tls")
def test_wrong_identity_grace_period(
    make_client: Callable[..., SocketClient], caplog: pytest.LogCaptureFixture
) -> None:
    """Test a wrong identity is warned about once, after the grace period."""
    client = make_client(tries=3)
    client.retry_wait = 0
    client.fn = "Kitchen"
    clock = [1000.0]
    results: list[DeviceAuthResult] = []

    def auth(*_args: Any, **_kwargs: Any) -> DeviceAuthResult:
        clock[0] += 400
        return results.pop(0)

    text = "is a genuine Cast device but not"
    with (
        patch("pychromecast.socket_client.time", _fake_time(clock)),
        patch("pychromecast.socket_client.authenticate", side_effect=auth),
        caplog.at_level(logging.DEBUG, logger="pychromecast.socket_client"),
    ):
        # Failing at 0 s, 400 s and 800 s into the streak
        results[:] = [_mismatch()] * 3
        with pytest.raises(ChromecastConnectionError):
            client.initialize_connection()
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert _retry_levels(caplog, text) == [
            logging.DEBUG,
            logging.DEBUG,
            logging.WARNING,
        ]
        assert f"Kitchen ({TEST_UUID})" in warnings[0].getMessage()
        assert f"it identifies as {LEADER_UUID}" in warnings[0].getMessage()
        assert "IP address change or group leader change" in warnings[0].getMessage()

        # Only one warning per streak
        client.stop.clear()
        results[:] = [_mismatch()] * 3
        with pytest.raises(ChromecastConnectionError):
            client.initialize_connection()
        assert _retry_levels(caplog, text) == [logging.DEBUG] * 3

        # Connecting ends the streak, a new streak warns again after the grace
        client.stop.clear()
        client.tries = 1
        results[:] = [VERIFIED]
        client.initialize_connection()
        client.tries = 3
        results[:] = [_mismatch()] * 3
        with pytest.raises(ChromecastConnectionError):
            client.initialize_connection()
        assert _retry_levels(caplog, text) == [
            logging.DEBUG,
            logging.DEBUG,
            logging.WARNING,
        ]


@pytest.mark.usefixtures("connect_patches", "fake_tls")
def test_group_network_failure_grace_period(
    make_client: Callable[..., SocketClient], caplog: pytest.LogCaptureFixture
) -> None:
    """Test network failures of a group are only logged after the grace period."""
    client = make_client(cast_type="group", tries=3)
    client.retry_wait = 0
    clock = [1000.0]

    def connect(*_args: Any, **_kwargs: Any) -> None:
        clock[0] += 400
        raise ConnectionRefusedError("refused")

    text = "Failed to connect to service"
    with (
        patch("pychromecast.socket_client.time", _fake_time(clock)),
        patch("socket.create_connection", side_effect=connect),
        caplog.at_level(logging.DEBUG, logger="pychromecast.socket_client"),
    ):
        with pytest.raises(ChromecastConnectionError):
            client.initialize_connection()
        assert _retry_levels(caplog, text) == [
            logging.DEBUG,
            logging.DEBUG,
            logging.INFO,
        ]

    # Connecting ends the streak, a new streak is logged after the grace again
    client.stop.clear()
    client.tries = 1
    with (
        patch("pychromecast.socket_client.time", _fake_time(clock)),
        patch("pychromecast.socket_client.authenticate", return_value=VERIFIED),
    ):
        client.initialize_connection()
    client.tries = 3
    with (
        patch("pychromecast.socket_client.time", _fake_time(clock)),
        patch("socket.create_connection", side_effect=connect),
        caplog.at_level(logging.DEBUG, logger="pychromecast.socket_client"),
    ):
        with pytest.raises(ChromecastConnectionError):
            client.initialize_connection()
        assert _retry_levels(caplog, text) == [
            logging.DEBUG,
            logging.DEBUG,
            logging.INFO,
        ]


@pytest.mark.usefixtures("fake_tls")
def test_auth_failure_uses_backoff(
    make_client: Callable[..., SocketClient], caplog: pytest.LogCaptureFixture
) -> None:
    """Test failures back off like network failures, without spinning."""
    client = make_client(tries=4, retry_wait=1)
    clock = [1000.0]
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock[0] += seconds

    fake_time = Mock()
    fake_time.time.side_effect = lambda: clock[0]
    fake_time.monotonic.side_effect = lambda: clock[0]
    fake_time.sleep.side_effect = sleep
    with (
        patch("pychromecast.socket_client.time", fake_time),
        patch(
            "pychromecast.socket_client.authenticate",
            return_value=_failure(DeviceAuthStatus.SIGNATURE_INVALID),
        ) as auth,
        caplog.at_level(logging.DEBUG, logger="pychromecast.socket_client"),
        pytest.raises(ChromecastConnectionError),
    ):
        client.initialize_connection()

    delays = [
        record.args[-1]  # type: ignore[index]
        for record in caplog.records
        if "may not be a genuine Cast device" in record.getMessage()
    ]
    assert delays == [1.0, 2.0, 4.0]
    assert auth.call_count == 3
    assert sleeps == [1, 1, 1]


@pytest.mark.usefixtures("connect_patches", "fake_tls")
@pytest.mark.parametrize("cast_type", ["cast", "group"])
def test_uuid_passed_for_all_endpoints(
    make_client: Callable[..., SocketClient], cast_type: str
) -> None:
    """Test the expected UUID is checked for devices and groups."""
    client = make_client(cast_type=cast_type)
    with (
        patch("pychromecast.socket_client.authenticate", return_value=VERIFIED) as auth,
        patch("pychromecast.socket_client.verify_group_leader") as verify_group,
    ):
        client.initialize_connection()
    assert auth.call_args.kwargs["expected_uuid"] == TEST_UUID
    # The certificate names the expected UUID, no attestation is needed
    verify_group.assert_not_called()


@pytest.mark.usefixtures("connect_patches", "fake_tls")
def test_device_uuid_mismatch_not_attested(
    make_client: Callable[..., SocketClient],
) -> None:
    """Test a device with the wrong identity is not checked as a group."""
    client = make_client()
    with (
        patch("pychromecast.socket_client.authenticate", return_value=_mismatch()),
        patch("pychromecast.socket_client.verify_group_leader") as verify_group,
        pytest.raises(ChromecastConnectionError),
    ):
        client.initialize_connection()
    verify_group.assert_not_called()
    assert client.device_auth_result is not None
    assert client.device_auth_result.status is DeviceAuthStatus.UUID_MISMATCH


@pytest.mark.usefixtures("connect_patches", "fake_tls")
def test_group_attested(make_client: Callable[..., SocketClient]) -> None:
    """Test a group served by a device which leads it."""
    client = make_client(cast_type="group")
    attested = DeviceAuthResult(DeviceAuthStatus.VERIFIED, "leads the group")
    with (
        patch("pychromecast.socket_client.authenticate", return_value=_mismatch()),
        patch(
            "pychromecast.socket_client.verify_group_leader", return_value=attested
        ) as verify_group,
    ):
        client.initialize_connection()
    verify_group.assert_called_once()
    assert verify_group.call_args.args == ("192.0.2.1", 8009, TEST_UUID, b"device cert")
    result = client.device_auth_result
    assert result is not None
    assert result.verified
    assert result.uuid_checked
    assert result.leader_uuid == LEADER_UUID
    assert result.detail == "leads the group"
    assert client.is_connected


@pytest.mark.usefixtures("connect_patches", "fake_tls")
def test_group_leader_change(
    make_client: Callable[..., SocketClient], caplog: pytest.LogCaptureFixture
) -> None:
    """Test a group whose leader changes during connecting recovers silently."""
    client = make_client(cast_type="group", tries=2)
    client.retry_wait = 0
    recorder = StatusRecorder()
    client.register_connection_listener(recorder)
    not_led = DeviceAuthResult(DeviceAuthStatus.GROUP_NOT_LED, "not the leader")
    attested = DeviceAuthResult(DeviceAuthStatus.VERIFIED, "leads the group")
    with (
        patch("pychromecast.socket_client.authenticate", return_value=_mismatch()),
        patch(
            "pychromecast.socket_client.verify_group_leader",
            side_effect=[not_led, attested],
        ),
        caplog.at_level(logging.DEBUG, logger="pychromecast.socket_client"),
    ):
        client.initialize_connection()
    assert recorder.names == [
        CONNECTION_STATUS_CONNECTING,
        CONNECTION_STATUS_FAILED_AUTH,
        CONNECTION_STATUS_CONNECTING,
        CONNECTION_STATUS_CONNECTED,
    ]
    failed = recorder.statuses[1].device_auth
    assert failed is not None
    assert failed.status is DeviceAuthStatus.GROUP_NOT_LED
    assert failed.failure_class is DeviceAuthFailureClass.WRONG_IDENTITY
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


@pytest.mark.usefixtures("connect_patches", "fake_tls")
def test_group_attestation_failure_retried(
    make_client: Callable[..., SocketClient],
) -> None:
    """Test a group which can't be attested fails authentication and is retried."""
    client = make_client(cast_type="group", tries=2)
    client.retry_wait = 0
    unavailable = DeviceAuthResult(
        DeviceAuthStatus.GROUP_ATTESTATION_UNAVAILABLE, "port 8443 is blocked"
    )
    with (
        patch(
            "pychromecast.socket_client.authenticate", return_value=_mismatch()
        ) as auth,
        patch(
            "pychromecast.socket_client.verify_group_leader", return_value=unavailable
        ),
        pytest.raises(ChromecastConnectionError),
    ):
        client.initialize_connection()
    assert auth.call_count == 2
    result = client.device_auth_result
    assert result is not None
    assert result.status is DeviceAuthStatus.GROUP_ATTESTATION_UNAVAILABLE
    # The genuine device's details are kept
    assert result.tls_cert_cn == str(LEADER_UUID)
    assert not result.uuid_checked


@pytest.mark.usefixtures("fake_tls")
def test_opt_out_skips_handshake(
    make_client: Callable[..., SocketClient], caplog: pytest.LogCaptureFixture
) -> None:
    """Test opting out skips device authentication."""
    with caplog.at_level(logging.INFO, logger="pychromecast.socket_client"):
        client = make_client(device_auth=False)
    # Opting out is intentional, it's logged but not warned about
    disabled = [
        record
        for record in caplog.records
        if "Cast device authentication is disabled" in record.getMessage()
    ]
    assert [record.levelno for record in disabled] == [logging.INFO]
    with (
        patch("pychromecast.socket_client.authenticate") as auth,
        patch.object(client.receiver_controller, "update_status") as update_status,
        patch.object(client.heartbeat_controller, "ping"),
    ):
        client.initialize_connection()
    auth.assert_not_called()
    update_status.assert_called_once()
    assert client.is_connected
    assert client.device_auth_result is not None
    assert client.device_auth_result.status is DeviceAuthStatus.DISABLED


def test_default_is_enabled() -> None:
    """Test device authentication is enabled by default."""
    client = SocketClient(
        cast_type="cast",
        tries=1,
        timeout=10,
        retry_wait=0.01,
        services=set(),
        zconf=None,
    )
    try:
        assert client.device_auth is True
        assert client.expected_uuid is None
        assert client.device_auth_result is None
    finally:
        _close_client(client)


def test_auth_network_error_reports_failed(
    make_client: Callable[..., SocketClient], fake_tls: FakeTLS
) -> None:
    """Test a network error during the handshake is a network failure."""
    client = make_client()
    recorder = StatusRecorder()
    client.register_connection_listener(recorder)
    with (
        patch(
            "pychromecast.socket_client.authenticate",
            side_effect=ConnectionResetError("reset"),
        ),
        pytest.raises(ChromecastConnectionError),
    ):
        client.initialize_connection()
    assert recorder.names == [CONNECTION_STATUS_CONNECTING, CONNECTION_STATUS_FAILED]
    assert fake_tls.tls_sockets[0].fileno() == -1
    assert client.socket is None


# Integration tests with a fake TLS receiver


def _json_message(namespace: str, data: dict) -> CastMessage:
    return CastMessage(
        protocol_version=CastMessage.CASTV2_1_0,
        source_id="receiver-0",
        destination_id="sender-0",
        namespace=namespace,
        payload_type=CastMessage.STRING,
        payload_utf8=json.dumps(data),
    )


def _receiver_status(request_id: int = 0) -> CastMessage:
    return _json_message(
        NS_RECEIVER,
        {
            "type": "RECEIVER_STATUS",
            "requestId": request_id,
            "status": {
                "volume": {"level": 0.5, "muted": False},
                "isActiveInput": True,
            },
        },
    )


class FakeReceiver(TLSServer):
    """A fake cast device, genuine or misbehaving depending on mode."""

    def __init__(
        self,
        pki: TestPKI,
        tmp_path: Path,
        mode: str = "genuine",
        tls_cn: str = str(TEST_UUID),
    ) -> None:
        self.pki = pki
        self.mode = mode
        self.tls_cert = make_tls_cert(tls_cn, pki.tls_key)
        # The messages received, per connection
        self.connections: list[list[CastMessage]] = []
        super().__init__(tmp_path, "receiver", self.tls_cert, pki.tls_key)

    def _auth_reply(self, nonce: bytes) -> list[CastMessage]:
        pki = self.pki
        kwargs: dict[str, Any] = {
            "nonce": nonce,
            "peer_cert_der": der(self.tls_cert),
            "leaf": pki.leaf,
            "leaf_key": pki.leaf_key,
            "intermediates": (pki.ica,),
        }
        if self.mode == "no_echo":
            kwargs["echo"] = False
        elif self.mode == "wrong_sig":
            kwargs["sign_over"] = b"something else"
        elif self.mode == "auth_error":
            kwargs["error"] = AuthError.INTERNAL_ERROR
        elif self.mode == "expired_ica":
            kwargs["intermediates"] = (
                make_cert(
                    "Test ICA",
                    pki.root,
                    pki.root_key,
                    pki.ica_key.public_key(),
                    ca=True,
                    path_length=0,
                    ku=key_usage(key_cert_sign=True),
                    not_before=NOW - timedelta(days=400),
                    not_after=NOW - timedelta(days=1),
                ),
            )
        reply = make_reply(**kwargs)
        if self.mode == "status_first":
            return [_receiver_status(), reply]
        return [reply]

    def handle(self, tls: ssl.SSLSocket) -> None:
        messages: list[CastMessage] = []
        self.connections.append(messages)
        buffer = b""
        while not self.stop.is_set():
            try:
                data = tls.recv(65536)
            except TimeoutError:
                continue
            if not data:
                return
            buffer += data
            while len(buffer) >= 4:
                (length,) = unpack(">I", buffer[:4])
                if len(buffer) < 4 + length:
                    break
                message = CastMessage()
                message.ParseFromString(buffer[4 : 4 + length])
                buffer = buffer[4 + length :]
                messages.append(message)
                if not self._respond(tls, message, first=len(messages) == 1):
                    return

    def _respond(self, tls: ssl.SSLSocket, message: CastMessage, first: bool) -> bool:
        """Respond to a message, return False to close the connection."""
        if message.namespace == NS_DEVICE_AUTH and first:
            if self.mode == "silent":
                return True
            if self.mode == "close":
                return False
            if self.mode == "slow":
                time.sleep(0.3)
            challenge = DeviceAuthMessage()
            challenge.ParseFromString(message.payload_binary)
            for reply in self._auth_reply(challenge.challenge.sender_nonce):
                tls.sendall(frame(reply))
            return True
        data = json.loads(message.payload_utf8 or "{}")
        if message.namespace == NS_RECEIVER and data.get("type") == "GET_STATUS":
            tls.sendall(frame(_receiver_status(data.get("requestId", 0))))
        elif message.namespace == NS_HEARTBEAT and data.get("type") == "PING":
            tls.sendall(frame(_json_message(NS_HEARTBEAT, {"type": "PONG"})))
        return True


class TLSRelay(TLSServer):
    """A relay with its own TLS certificate, forwarding to a receiver."""

    def __init__(self, tmp_path: Path, upstream_port: int) -> None:
        key = rsa_key()
        self.upstream_port = upstream_port
        super().__init__(tmp_path, "relay", make_tls_cert(str(TEST_UUID), key), key)

    def handle(self, tls: ssl.SSLSocket) -> None:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        upstream = context.wrap_socket(
            socket.create_connection(("127.0.0.1", self.upstream_port), 2)
        )
        upstream.settimeout(0.05)
        peers = {tls: upstream, upstream: tls}
        try:
            # One thread, SSL sockets must not be read and written concurrently
            while not self.stop.is_set():
                readable = [sock for sock in peers if sock.pending()]
                if not readable:
                    readable, _, _ = select.select(list(peers), [], [], 0.05)
                for source in readable:
                    try:
                        data = source.recv(65536)
                    except TimeoutError, ssl.SSLWantReadError:
                        continue
                    if not data:
                        return
                    peers[source].sendall(data)
        finally:
            upstream.close()


@pytest.fixture(name="receiver_factory")
def receiver_factory_fixture(
    pki: TestPKI, tmp_path: Path
) -> Generator[Callable[..., FakeReceiver]]:
    """Return a factory of fake receivers, stopped after the test."""
    servers: list[TLSServer] = []

    def make(mode: str = "genuine", **kwargs: Any) -> FakeReceiver:
        receiver = FakeReceiver(pki, tmp_path, mode, **kwargs)
        servers.append(receiver)
        return receiver

    yield make
    for server in servers:
        server.close()


@pytest.fixture(name="default_eureka", autouse=True)
def default_eureka_fixture(
    eureka_factory: Callable[..., EurekaServer],
) -> Generator[EurekaServer]:
    """Serve the eureka_info of the test device, which leads no group."""
    server = eureka_factory()
    with patch("pychromecast.device_auth.GROUP_ATTESTATION_PORT", server.port):
        yield server


def _e2e_client(
    make_client: Callable[..., SocketClient], pki: TestPKI, port: int, **kwargs: Any
) -> SocketClient:
    options: dict[str, Any] = {
        "services": {HostServiceInfo("127.0.0.1", port)},
        "timeout": 2,
        "device_auth_trust_roots": [pki.root],
    }
    options.update(kwargs)
    return make_client(**options)


def _is_challenge(message: CastMessage) -> bool:
    if message.namespace != NS_DEVICE_AUTH:
        return False
    auth_message = DeviceAuthMessage()
    auth_message.ParseFromString(message.payload_binary)
    return auth_message.HasField("challenge")


def _nonce(message: CastMessage) -> bytes:
    auth_message = DeviceAuthMessage()
    auth_message.ParseFromString(message.payload_binary)
    return auth_message.challenge.sender_nonce


def _wait_for(condition: Callable[[], bool], timeout: float = 5) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.01)


def test_e2e_genuine_connects(
    make_client: Callable[..., SocketClient],
    receiver_factory: Callable[..., FakeReceiver],
    pki: TestPKI,
) -> None:
    """Test connecting to a genuine device."""
    receiver = receiver_factory()
    client = _e2e_client(make_client, pki, receiver.port)
    client.initialize_connection()

    assert client.is_connected
    assert client.device_auth_result is not None
    assert client.device_auth_result.verified
    assert client.device_auth_result.uuid_checked
    _wait_for(
        lambda: len(receiver.connections) == 1 and len(receiver.connections[0]) >= 2
    )
    messages = receiver.connections[0]
    assert _is_challenge(messages[0])
    assert messages[1].namespace == NS_CONNECTION
    assert json.loads(messages[1].payload_utf8)["type"] == "CONNECT"


def test_e2e_genuine_threaded(
    make_client: Callable[..., SocketClient],
    receiver_factory: Callable[..., FakeReceiver],
    pki: TestPKI,
) -> None:
    """Test a genuine device through the worker thread."""
    receiver = receiver_factory()
    client = _e2e_client(make_client, pki, receiver.port)
    recorder = StatusRecorder()
    client.register_connection_listener(recorder)
    received: list[CastStatus] = []
    status_event = threading.Event()

    class Listener:
        def new_cast_status(self, status: CastStatus) -> None:
            received.append(status)
            status_event.set()

    client.receiver_controller.register_status_listener(Listener())  # type: ignore[arg-type]
    client.start()
    try:
        assert recorder.connected.wait(5)
        assert status_event.wait(5)
        assert received[0].volume_level == 0.5
        connected = [
            s for s in recorder.statuses if s.status == CONNECTION_STATUS_CONNECTED
        ]
        assert connected[0].device_auth is not None
        assert connected[0].device_auth.verified
    finally:
        client.disconnect()
        client.join(5)
    assert not client.is_alive()


@pytest.mark.parametrize(
    ("mode", "kwargs", "status"),
    [
        ("no_echo", {}, DeviceAuthStatus.NONCE_MISSING),
        ("wrong_sig", {}, DeviceAuthStatus.SIGNATURE_INVALID),
        ("auth_error", {}, DeviceAuthStatus.AUTH_ERROR_REPLY),
        ("status_first", {}, DeviceAuthStatus.UNEXPECTED_MESSAGE),
        ("silent", {}, DeviceAuthStatus.NO_REPLY),
        ("close", {}, DeviceAuthStatus.CONNECTION_CLOSED),
        ("expired_ica", {}, DeviceAuthStatus.CERT_EXPIRED),
        ("genuine", {"tls_cn": str(OTHER_UUID)}, DeviceAuthStatus.UUID_MISMATCH),
    ],
)
def test_e2e_rejected(
    make_client: Callable[..., SocketClient],
    receiver_factory: Callable[..., FakeReceiver],
    pki: TestPKI,
    mode: str,
    kwargs: dict,
    status: DeviceAuthStatus,
) -> None:
    """Test a device failing authentication only receives the challenge."""
    receiver = receiver_factory(mode, **kwargs)
    client = _e2e_client(make_client, pki, receiver.port)
    with (
        patch("pychromecast.socket_client.DEVICE_AUTH_TIMEOUT", 0.5),
        pytest.raises(ChromecastConnectionError),
    ):
        client.initialize_connection()

    receiver.wait_idle()
    assert len(receiver.connections) == 1
    messages = receiver.connections[0]
    assert len(messages) == 1
    assert _is_challenge(messages[0])
    assert client.device_auth_result is not None
    assert client.device_auth_result.status is status


def test_e2e_relay_rejected(
    make_client: Callable[..., SocketClient],
    receiver_factory: Callable[..., FakeReceiver],
    pki: TestPKI,
    tmp_path: Path,
) -> None:
    """Test a relay to a genuine device, with its own TLS certificate, is rejected."""
    receiver = receiver_factory()
    relay = TLSRelay(tmp_path, receiver.port)
    try:
        client = _e2e_client(make_client, pki, relay.port)
        with pytest.raises(ChromecastConnectionError):
            client.initialize_connection()
        assert client.device_auth_result is not None
        assert client.device_auth_result.status is DeviceAuthStatus.SIGNATURE_INVALID
        relay.wait_idle()
        receiver.wait_idle()
        assert len(receiver.connections) == 1
        assert len(receiver.connections[0]) == 1
        assert _is_challenge(receiver.connections[0][0])
    finally:
        relay.close()


def test_e2e_opt_out_talks_to_fake(
    make_client: Callable[..., SocketClient],
    receiver_factory: Callable[..., FakeReceiver],
    pki: TestPKI,
) -> None:
    """Test opting out connects to a device which would fail authentication."""
    receiver = receiver_factory("wrong_sig")
    client = _e2e_client(make_client, pki, receiver.port, device_auth=False)
    client.initialize_connection()

    assert client.is_connected
    assert client.device_auth_result is not None
    assert client.device_auth_result.status is DeviceAuthStatus.DISABLED
    _wait_for(
        lambda: len(receiver.connections) == 1 and len(receiver.connections[0]) >= 1
    )
    first = receiver.connections[0][0]
    assert first.namespace == NS_CONNECTION
    assert not any(m.namespace == NS_DEVICE_AUTH for m in receiver.connections[0])


def test_e2e_reauth_on_reconnect(
    make_client: Callable[..., SocketClient],
    receiver_factory: Callable[..., FakeReceiver],
    pki: TestPKI,
) -> None:
    """Test the device is authenticated again on reconnect."""
    receiver = receiver_factory()
    client = _e2e_client(make_client, pki, receiver.port)
    client.initialize_connection()
    client._force_recon = True  # pylint: disable=protected-access
    assert not client._check_connection()  # pylint: disable=protected-access

    assert client.is_connected
    _wait_for(lambda: len(receiver.connections) == 2 and bool(receiver.connections[1]))
    first, second = receiver.connections[0][0], receiver.connections[1][0]
    assert _is_challenge(first)
    assert _is_challenge(second)
    assert _nonce(first) != _nonce(second)


def test_e2e_send_during_auth_raises(
    make_client: Callable[..., SocketClient],
    receiver_factory: Callable[..., FakeReceiver],
    pki: TestPKI,
) -> None:
    """Test other threads can't send while the device is being authenticated."""
    receiver = receiver_factory("slow")
    client = _e2e_client(make_client, pki, receiver.port)
    thread = threading.Thread(target=client.initialize_connection)
    thread.start()
    try:
        _wait_for(lambda: bool(receiver.connections and receiver.connections[0]))
        with pytest.raises(NotConnected):
            client.send_message(
                "receiver-0",
                NS_RECEIVER,
                {"type": "GET_STATUS"},
                no_add_request_id=True,
            )
        # The challenge, nothing else is sent before the reply
        assert len(receiver.connections[0]) == 1
    finally:
        thread.join(5)
    assert client.is_connected
    _wait_for(lambda: len(receiver.connections[0]) >= 2)
    assert _is_challenge(receiver.connections[0][0])
    assert receiver.connections[0][1].namespace == NS_CONNECTION


def test_e2e_selector_not_registered_on_failure(
    make_client: Callable[..., SocketClient],
    receiver_factory: Callable[..., FakeReceiver],
    pki: TestPKI,
) -> None:
    """Test a device failing authentication is never registered with the selector."""
    receiver = receiver_factory("wrong_sig")
    client = _e2e_client(make_client, pki, receiver.port)
    with (
        patch.object(client.selector, "register") as register,
        pytest.raises(ChromecastConnectionError),
    ):
        client.initialize_connection()
    register.assert_not_called()
    assert list(client.selector.get_map().values()) == [client.wakeup_selector_key]


def test_e2e_group_endpoint_with_own_uuid(
    make_client: Callable[..., SocketClient],
    receiver_factory: Callable[..., FakeReceiver],
    eureka_factory: Callable[..., EurekaServer],
    pki: TestPKI,
) -> None:
    """Test an endpoint labelled a group which presents the expected UUID.

    The port is not 8009, the device's groups are checked, it leads none there.
    """
    receiver = receiver_factory()
    eureka = eureka_factory(body=eureka_info([group_entry(1)]))
    client = _e2e_client(make_client, pki, receiver.port, cast_type="group")
    with patch("pychromecast.device_auth.GROUP_ATTESTATION_PORT", eureka.port):
        client.initialize_connection()

    assert client.is_connected
    assert client.device_auth_result is not None
    assert client.device_auth_result.uuid_checked
    assert client.device_auth_result.leader_uuid is None
    assert len(eureka.requests) == 1


def test_e2e_group_attested(
    make_client: Callable[..., SocketClient],
    receiver_factory: Callable[..., FakeReceiver],
    eureka_factory: Callable[..., EurekaServer],
    pki: TestPKI,
) -> None:
    """Test a group served by its leader."""
    receiver = receiver_factory(tls_cn=str(OTHER_UUID))
    eureka = eureka_factory(body=eureka_info([group_entry(receiver.port)]))
    client = _e2e_client(make_client, pki, receiver.port, cast_type="group")
    with patch("pychromecast.device_auth.GROUP_ATTESTATION_PORT", eureka.port):
        client.initialize_connection()

    assert client.is_connected
    result = client.device_auth_result
    assert result is not None
    assert result.verified
    assert result.uuid_checked
    assert result.leader_uuid == OTHER_UUID
    assert eureka.requests == [b"GET /setup/eureka_info?params=multizone HTTP/1.1"]


@pytest.mark.parametrize(
    ("entry", "status"),
    [
        ({"elected_leader": "[::ffff:c0a8:a1]:10001"}, DeviceAuthStatus.GROUP_NOT_LED),
        ({"cast_port": 1}, DeviceAuthStatus.GROUP_PORT_MISMATCH),
        ({"uuid": str(OTHER_UUID)}, DeviceAuthStatus.GROUP_NOT_LED),
    ],
)
def test_e2e_group_not_attested(
    make_client: Callable[..., SocketClient],
    receiver_factory: Callable[..., FakeReceiver],
    eureka_factory: Callable[..., EurekaServer],
    pki: TestPKI,
    entry: dict[str, Any],
    status: DeviceAuthStatus,
) -> None:
    """Test a group which is not led by the device only receives the challenge."""
    receiver = receiver_factory(tls_cn=str(OTHER_UUID))
    eureka = eureka_factory(body=eureka_info([group_entry(receiver.port, **entry)]))
    client = _e2e_client(make_client, pki, receiver.port, cast_type="group", tries=2)
    client.retry_wait = 0
    with (
        patch("pychromecast.device_auth.GROUP_ATTESTATION_PORT", eureka.port),
        pytest.raises(ChromecastConnectionError),
    ):
        client.initialize_connection()

    assert client.device_auth_result is not None
    assert client.device_auth_result.status is status
    receiver.wait_idle()
    # Retried, and each connection only received the challenge
    assert len(receiver.connections) == 2
    for messages in receiver.connections:
        assert len(messages) == 1
        assert _is_challenge(messages[0])
    assert len(eureka.requests) == 2


def test_e2e_group_attestation_unavailable(
    make_client: Callable[..., SocketClient],
    receiver_factory: Callable[..., FakeReceiver],
    pki: TestPKI,
) -> None:
    """Test a group whose leader's port 8443 can't be reached fails closed."""
    receiver = receiver_factory(tls_cn=str(OTHER_UUID))
    client = _e2e_client(make_client, pki, receiver.port, cast_type="group")
    with (
        refused_port() as port,
        patch("pychromecast.device_auth.GROUP_ATTESTATION_PORT", port),
        pytest.raises(ChromecastConnectionError),
    ):
        client.initialize_connection()

    assert client.device_auth_result is not None
    assert (
        client.device_auth_result.status
        is DeviceAuthStatus.GROUP_ATTESTATION_UNAVAILABLE
    )
    receiver.wait_idle()
    assert len(receiver.connections[0]) == 1


@pytest.mark.usefixtures("fake_tls")
def test_final_error_carries_result(
    make_client: Callable[..., SocketClient],
) -> None:
    """Test running out of retries raises the device authentication result."""
    client = make_client()
    result = _failure(DeviceAuthStatus.CHAIN_UNTRUSTED)
    with (
        patch("pychromecast.socket_client.authenticate", return_value=result),
        pytest.raises(DeviceAuthenticationError) as err,
    ):
        client.initialize_connection()
    assert err.value.result is result


@pytest.mark.usefixtures("fake_tls", "connect_patches")
def test_auth_result_reset_per_attempt(
    make_client: Callable[..., SocketClient],
) -> None:
    """Test a network failure after an auth failure is not blamed on auth."""
    client = make_client(tries=2)
    client.retry_wait = 0
    with (
        patch(
            "socket.create_connection",
            side_effect=[MagicMock(), ConnectionRefusedError("refused")],
        ),
        patch(
            "pychromecast.socket_client.authenticate",
            return_value=_failure(DeviceAuthStatus.CHAIN_UNTRUSTED),
        ),
        pytest.raises(ChromecastConnectionError) as err,
    ):
        client.initialize_connection()
    assert not isinstance(err.value, DeviceAuthenticationError)
    assert client.device_auth_result is None


@pytest.mark.usefixtures("fake_tls", "connect_patches")
def test_device_endpoint_on_group_port_refused(
    make_client: Callable[..., SocketClient],
) -> None:
    """Test a device's own UUID on the port of a group it leads is refused."""
    client = make_client(services={HostServiceInfo("192.0.2.1", 32149)})
    group_endpoint = DeviceAuthResult(
        DeviceAuthStatus.GROUP_ENDPOINT, "port 32149 is the port of a group"
    )
    verified = replace(VERIFIED, device_cert_der=b"device cert")
    with (
        patch("pychromecast.socket_client.authenticate", return_value=verified),
        patch(
            "pychromecast.socket_client.verify_not_group_endpoint",
            return_value=group_endpoint,
        ) as check,
        pytest.raises(DeviceAuthenticationError),
    ):
        client.initialize_connection()
    assert check.call_args.args == ("192.0.2.1", 32149, b"device cert")
    result = client.device_auth_result
    assert result is not None
    assert result.status is DeviceAuthStatus.GROUP_ENDPOINT
    assert result.failure_class is DeviceAuthFailureClass.WRONG_IDENTITY
    assert result.tls_cert_cn == str(TEST_UUID)
    assert not result.uuid_checked


@pytest.mark.usefixtures("fake_tls", "connect_patches")
@pytest.mark.parametrize(("port", "expected_uuid"), [(8009, TEST_UUID), (32149, None)])
def test_device_endpoint_check_skipped(
    make_client: Callable[..., SocketClient], port: int, expected_uuid: UUID | None
) -> None:
    """Test the groups are not checked on port 8009, or without expected UUID."""
    client = make_client(
        services={HostServiceInfo("192.0.2.1", port)}, expected_uuid=expected_uuid
    )
    verified = replace(VERIFIED, uuid_checked=expected_uuid is not None)
    with (
        patch("pychromecast.socket_client.authenticate", return_value=verified),
        patch("pychromecast.socket_client.verify_not_group_endpoint") as check,
    ):
        client.initialize_connection()
    check.assert_not_called()
    assert client.is_connected


@pytest.mark.usefixtures("fake_tls", "connect_patches")
def test_device_endpoint_check_passes(
    make_client: Callable[..., SocketClient],
) -> None:
    """Test a device on another port which leads no group there is accepted."""
    client = make_client(services={HostServiceInfo("192.0.2.1", 8010)})
    ok = DeviceAuthResult(DeviceAuthStatus.VERIFIED, "not a group port")
    with (
        patch("pychromecast.socket_client.authenticate", return_value=VERIFIED),
        patch(
            "pychromecast.socket_client.verify_not_group_endpoint", return_value=ok
        ) as check,
    ):
        client.initialize_connection()
    check.assert_called_once()
    assert client.device_auth_result is VERIFIED


def test_e2e_device_endpoint_on_group_port(
    make_client: Callable[..., SocketClient],
    receiver_factory: Callable[..., FakeReceiver],
    default_eureka: EurekaServer,
    pki: TestPKI,
) -> None:
    """Test the port of a group the device leads is refused for the device."""
    receiver = receiver_factory()
    default_eureka.body = eureka_info([group_entry(receiver.port)])
    client = _e2e_client(make_client, pki, receiver.port)
    with pytest.raises(DeviceAuthenticationError):
        client.initialize_connection()

    assert client.device_auth_result is not None
    assert client.device_auth_result.status is DeviceAuthStatus.GROUP_ENDPOINT
    receiver.wait_idle()
    assert len(receiver.connections[0]) == 1
    assert _is_challenge(receiver.connections[0][0])
    assert len(default_eureka.requests) == 1


def test_e2e_group_not_genuine(
    make_client: Callable[..., SocketClient],
    receiver_factory: Callable[..., FakeReceiver],
    default_eureka: EurekaServer,
    pki: TestPKI,
) -> None:
    """Test a group endpoint which is not genuine never gets the eureka request."""
    receiver = receiver_factory("wrong_sig", tls_cn=str(OTHER_UUID))
    client = _e2e_client(make_client, pki, receiver.port, cast_type="group")
    with pytest.raises(DeviceAuthenticationError):
        client.initialize_connection()

    assert client.device_auth_result is not None
    assert client.device_auth_result.status is DeviceAuthStatus.SIGNATURE_INVALID
    receiver.wait_idle()
    assert len(receiver.connections[0]) == 1
    default_eureka.wait_idle()
    assert default_eureka.handlers == []
