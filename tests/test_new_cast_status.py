"""Tests for how the socket client follows the running app."""

from collections.abc import Generator
from struct import unpack

import pytest

from pychromecast.controllers.receiver import CastStatus
from pychromecast.generated.cast_channel_pb2 import (  # pylint: disable=no-name-in-module
    CastMessage,
)
from pychromecast.socket_client import NS_CONNECTION, SocketClient

NS_MEDIA = "urn:x-cast:com.google.cast.media"


class FakeSocket:
    """Socket recording written messages."""

    def __init__(self) -> None:
        self.sent: list[CastMessage] = []

    def sendall(self, data: bytes) -> None:
        """Record a written message."""
        (length,) = unpack(">I", data[:4])
        msg = CastMessage()
        msg.ParseFromString(data[4 : 4 + length])
        self.sent.append(msg)


def _status(session_id: str, transport_id: str, app_id: str) -> CastStatus:
    return CastStatus(
        is_active_input=None,
        is_stand_by=None,
        volume_level=0.5,
        volume_muted=False,
        app_id=app_id,
        display_name="Spotify",
        namespaces=[NS_MEDIA],
        session_id=session_id,
        transport_id=transport_id,
        status_text="",
        icon_url=None,
        volume_control_type="attenuation",
    )


@pytest.fixture(name="client")
def client_fixture() -> Generator[SocketClient]:
    """Return a socket client with a fake socket."""
    client = SocketClient(
        cast_type="audio",
        tries=1,
        timeout=1,
        retry_wait=1,
        services=set(),
        zconf=None,
    )
    client.connecting = False
    client.socket = FakeSocket()  # type: ignore[assignment]
    yield client
    client.socketpair[0].close()
    client.socketpair[1].close()
    client.selector.close()


def _sent(client: SocketClient) -> list[tuple[str, str, str]]:
    sock = client.socket
    assert isinstance(sock, FakeSocket)
    sent = [
        (msg.destination_id, msg.namespace, msg.payload_utf8.split('"')[3])
        for msg in sock.sent
    ]
    sock.sent.clear()
    return sent


def test_new_app_on_same_transport(client: SocketClient) -> None:
    """Test the app channel is reconnected when the session changes.

    A group member taking over the group's session runs the session's app on
    the transport of the app it ran as a member.
    """
    client.new_cast_status(_status("member-session", "transport", "705D30C6"))
    assert _sent(client) == [
        ("transport", NS_CONNECTION, "CONNECT"),
        ("transport", NS_MEDIA, "GET_STATUS"),
    ]

    client.new_cast_status(_status("group-session", "transport", "CC32E753"))

    assert _sent(client) == [
        ("transport", NS_CONNECTION, "CLOSE"),
        ("transport", NS_CONNECTION, "CONNECT"),
        ("transport", NS_MEDIA, "GET_STATUS"),
    ]
    assert client.session_id == "group-session"


def test_same_app(client: SocketClient) -> None:
    """Test nothing is sent when the status of the running app is unchanged."""
    client.new_cast_status(_status("session", "transport", "CC32E753"))
    _sent(client)

    client.new_cast_status(_status("session", "transport", "CC32E753"))

    assert not _sent(client)
