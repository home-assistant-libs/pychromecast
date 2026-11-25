"""Tests for pychromecast.dial."""

from collections.abc import Iterator
from dataclasses import replace
import json
from struct import pack, unpack
from typing import Any, Self
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch
from uuid import UUID

from google.protobuf.message import DecodeError
import pytest

from pychromecast.const import (
    CAST_TYPE_AUDIO,
    CAST_TYPE_CHROMECAST,
    CAST_TYPE_GROUP,
    CastCapability,
)
from pychromecast.dial import (
    NS_SETUP,
    EurekaGroup,
    _get_eureka_info,
    _get_eureka_info_cast,
    _get_group_info,
    _url_encode_hostname,
    _url_host_header,
    get_cast_type,
    get_device_info,
    get_host_from_zc_service_info,
    get_multizone_status,
)
from pychromecast.generated.cast_channel_pb2 import (  # pylint: disable=no-name-in-module
    CastMessage,
)
from pychromecast.models import CastInfo, HostServiceInfo
from pychromecast.protocol import NS_CONNECTION, connect_message


@pytest.fixture(name="no_cast_eureka_info", autouse=True)
def fixture_no_cast_eureka_info() -> Iterator[MagicMock]:
    """Fail eureka_info over cast, so it's fetched over HTTP."""
    with patch(
        "pychromecast.dial._get_eureka_info_cast",
        side_effect=OSError("no cast connection"),
    ) as get_eureka_info_cast:
        yield get_eureka_info_cast


HOSTNAMES = [
    # (hostname, hostname encoded for use in a url)
    ("192.168.1.2", "192.168.1.2"),
    ("chromecast.local", "chromecast.local"),
    ("2001:db8::1", "[2001:db8::1]"),
    ("fe80::1%2", "[fe80::1%252]"),
    ("fe80::1%en0", "[fe80::1%25en0]"),
]


@pytest.mark.parametrize(("hostname", "encoded"), HOSTNAMES)
def test_url_encode_hostname(hostname: str, encoded: str) -> None:
    """Test that ipv6 addresses are enclosed and zone identifiers encoded."""
    assert _url_encode_hostname(hostname) == encoded


@pytest.mark.parametrize(("hostname", "encoded"), HOSTNAMES)
def test_get_group_info_elected_leader(hostname: str, encoded: str) -> None:
    """Test that the leader host is extracted from the elected leader.

    The zone of a link local leader is local to the device, so it's dropped.
    """
    group: EurekaGroup = {"elected_leader": f"{encoded}:8009"}
    assert _get_group_info("10.0.0.1", group).host == hostname.partition("%")[0]


@pytest.mark.parametrize(
    ("host", "elected_leader", "leader_host"),
    [
        ("fe80::a%2", "[fe80::b]:8009", "fe80::b%2"),
        ("fe80::a%en0", "[fe80::b]:8009", "fe80::b%en0"),
        # A scope reported by the device is local to it and replaced
        ("fe80::a%2", "[fe80::b%253]:8009", "fe80::b%2"),
        ("fe80::a", "[fe80::b%253]:8009", "fe80::b"),
        # Only link local addresses need a scope
        ("fe80::a%2", "[2001:db8::b]:8009", "2001:db8::b"),
        ("fe80::a%2", "192.168.1.3:8009", "192.168.1.3"),
        # Nothing to inherit
        ("fe80::a", "[fe80::b]:8009", "fe80::b"),
        ("192.168.1.2", "[fe80::b]:8009", "fe80::b"),
        ("chromecast.local", "[fe80::b]:8009", "fe80::b"),
        ("chromecast.local", "[fe80::b%253]:8009", "fe80::b"),
    ],
)
def test_get_group_info_elected_leader_scope(
    host: str, elected_leader: str, leader_host: str
) -> None:
    """Test that an unscoped link local leader inherits the polled host's scope."""
    group: EurekaGroup = {"elected_leader": elected_leader}
    assert _get_group_info(host, group).host == leader_host


@pytest.mark.parametrize(
    ("elected_leader", "leader_host"),
    [
        ("chromecast.local:8009", "chromecast.local"),
        # Malformed values give no leader instead of failing all groups
        ("[fe80::b:8009", None),
        ("[]:8009", None),
        (":8009", None),
    ],
)
def test_get_group_info_elected_leader_format(
    elected_leader: str, leader_host: str | None
) -> None:
    """Test parsing of elected leaders in other formats."""
    group: EurekaGroup = {"elected_leader": elected_leader}
    assert _get_group_info("10.0.0.1", group).host == leader_host


def test_get_group_info_elected_leader_self() -> None:
    """Test that a self elected leader uses the host and cast port."""
    group: EurekaGroup = {"elected_leader": "self", "cast_port": 32187}
    info = _get_group_info("10.0.0.1", group)
    assert (info.host, info.port) == ("10.0.0.1", 32187)


@pytest.mark.parametrize(
    ("group", "leader_host"),
    [
        # Static groups report the leader in elected_leader, and leader empty
        ({"elected_leader": "10.0.0.2:10001", "leader": ""}, "10.0.0.2"),
        # Dynamic groups report the leader in leader
        ({"leader": "10.0.0.2:10001"}, "10.0.0.2"),
        # Dynamic groups have no cast port, so the port of a leader is unknown
        ({"leader": "self"}, None),
        ({}, None),
    ],
)
def test_get_group_info_leader(group: EurekaGroup, leader_host: str | None) -> None:
    """Test that the leader of static and dynamic groups is found."""
    assert _get_group_info("10.0.0.1", group).host == leader_host


@pytest.mark.parametrize(("hostname", "encoded"), HOSTNAMES)
def test_urllib_decodes_encoded_hostname(hostname: str, encoded: str) -> None:
    """Test that urllib connects to the original hostname of an encoded url."""
    request = urllib.request.Request(f"https://{encoded}:8443/setup/eureka_info")
    expected = f"[{hostname}]" if ":" in hostname else hostname
    assert request.host == f"{expected}:8443"


@pytest.mark.parametrize(
    ("url", "host_header"),
    [
        ("https://192.168.1.2:8443/setup/eureka_info", "192.168.1.2:8443"),
        ("http://192.168.1.2:8008/setup/eureka_info", "192.168.1.2:8008"),
        ("http://chromecast.local:8008/setup/eureka_info", "chromecast.local:8008"),
        ("https://[2001:db8::1]:8443/setup/eureka_info", "[2001:db8::1]:8443"),
        # The zone identifier is only meaningful locally and must not be sent
        ("https://[fe80::1%252]:8443/setup/eureka_info", "[fe80::1]:8443"),
        ("https://[fe80::1%25en0]:8443/setup/eureka_info", "[fe80::1]:8443"),
        # Default ports are left out
        ("http://chromecast.local:80/", "chromecast.local"),
        ("https://chromecast.local:443/", "chromecast.local"),
        ("https://chromecast.local/", "chromecast.local"),
    ],
)
def test_url_host_header(url: str, host_header: str) -> None:
    """Test the host header constructed from a url."""
    assert _url_host_header(url) == host_header


def _service_info(port: int | None, addresses: list[str]) -> MagicMock:
    """Return a mock zeroconf ServiceInfo."""
    service_info = MagicMock()
    service_info.port = port
    service_info.parsed_scoped_addresses.return_value = addresses
    return service_info


@pytest.mark.parametrize(
    ("port", "addresses", "expected"),
    [
        # zeroconf lists IPv4 before IPv6, so IPv4 is preferred
        (8009, ["192.168.1.2", "fe80::1%2"], ("192.168.1.2", 8009)),
        (8009, ["fe80::1%2", "2001:db8::1"], ("fe80::1%2", 8009)),
        (8009, [], (None, None)),
        (None, ["192.168.1.2"], (None, None)),
    ],
)
def test_get_host_from_zc_service_info(
    port: int | None, addresses: list[str], expected: tuple[str | None, int | None]
) -> None:
    """Test that the first address zeroconf reports is used."""
    assert get_host_from_zc_service_info(_service_info(port, addresses)) == expected


def test_get_host_from_zc_service_info_none() -> None:
    """Test that a missing service info gives no host."""
    assert get_host_from_zc_service_info(None) == (None, None)


MAC_ADDRESS = "00:00:5E:00:53:01"
UUID_STR = "12345678-1234-1234-1234-123456789abc"

STATUS: dict[str, Any] = {
    "name": "Speaker",
    "device_info": {
        "mac_address": MAC_ADDRESS,
        "product_name": "product",
        "ssdp_udn": UUID_STR,
    },
    "build_info": {"cast_build_revision": "1.2.3"},
}


def test_get_device_info_details() -> None:
    """Test that device details are read from device_info and build_info."""
    with patch(
        "pychromecast.dial._get_status", return_value=("192.0.2.1", STATUS)
    ) as get_status:
        device_status = get_device_info("192.0.2.1")
    assert get_status.call_args[0][2] == (
        "/setup/eureka_info?params=device_info,name,build_info"
    )
    assert device_status is not None
    assert device_status.mac_address == MAC_ADDRESS
    assert device_status.product_name == "product"
    assert device_status.cast_build_revision == "1.2.3"


def test_get_device_info_no_details() -> None:
    """Test that missing device details give None."""
    status = {"name": "Speaker", "device_info": {}}
    with patch("pychromecast.dial._get_status", return_value=("192.0.2.1", status)):
        device_status = get_device_info("192.0.2.1")
    assert device_status is not None
    assert device_status.mac_address is None
    assert device_status.product_name is None
    assert device_status.cast_build_revision is None


def _cast_info(port: int = 8009) -> CastInfo:
    return CastInfo(
        {HostServiceInfo("192.0.2.1", port)},
        UUID(UUID_STR),
        "Chromecast Audio",
        "Speaker",
        "192.0.2.1",
        port,
        None,
        None,
    )


def test_get_cast_type_keeps_details() -> None:
    """Test that get_cast_type fills in the type and manufacturer only."""
    status = {
        **STATUS,
        "device_info": {
            **STATUS["device_info"],
            "capabilities": {"display_supported": False},
            "manufacturer": "Google Inc.",
        },
    }
    cast_info = replace(_cast_info(), mac_address="00:00:5E:00:53:02")
    with patch(
        "pychromecast.dial._get_status", return_value=("192.0.2.1", status)
    ) as get_status:
        result = get_cast_type(cast_info)
    assert get_status.call_args[0][2] == "/setup/eureka_info?params=device_info,name"
    assert result.cast_type == CAST_TYPE_AUDIO
    assert result.manufacturer == "Google Inc."
    assert result.mac_address == "00:00:5E:00:53:02"
    assert result.product_name is None
    assert result.cast_build_revision is None


def test_get_cast_type_display() -> None:
    """Test that a device with a display is a chromecast."""
    with patch("pychromecast.dial._get_status", return_value=("192.0.2.1", STATUS)):
        result = get_cast_type(_cast_info())
    assert result.cast_type == CAST_TYPE_CHROMECAST
    assert result.manufacturer == "Unknown manufacturer"


def test_get_cast_type_group() -> None:
    """Test that a group is not queried."""
    with patch("pychromecast.dial._get_status") as get_status:
        result = get_cast_type(_cast_info(port=32000))
    get_status.assert_not_called()
    assert result.cast_type == CAST_TYPE_GROUP
    assert result.manufacturer == "Google Inc."


@pytest.mark.parametrize(
    "side_effect",
    [
        urllib.error.URLError("unreachable"),
        ValueError("not json"),
    ],
)
def test_get_cast_type_failed(side_effect: Any) -> None:
    """Test the defaults when the device info can't be fetched."""
    cast_info = replace(
        _cast_info(), mac_address=MAC_ADDRESS, cast_build_revision="1.2.3"
    )
    with patch("pychromecast.dial._get_status", side_effect=side_effect):
        result = get_cast_type(cast_info)
    assert result.cast_type == CAST_TYPE_CHROMECAST
    assert result.manufacturer == "Unknown manufacturer"
    # Known details are kept
    assert result.mac_address == MAC_ADDRESS
    assert result.cast_build_revision == "1.2.3"


SERVICES: set[HostServiceInfo | Any] = {HostServiceInfo("192.0.2.1", 8009)}


def test_get_eureka_info_falls_back_to_http(no_cast_eureka_info: MagicMock) -> None:
    """Test that eureka_info is requested over HTTPS, then HTTP, if cast fails."""
    with patch(
        "pychromecast.dial._get_status",
        side_effect=[urllib.error.URLError("no https"), ("192.0.2.1", STATUS)],
    ) as get_status:
        status = _get_eureka_info(SERVICES, None, ["device_info", "name"], 30, None)
    assert status == STATUS
    assert no_cast_eureka_info.call_args[0][:4] == (
        "192.0.2.1",
        8009,
        ["device_info", "name"],
        10,
    )
    assert [call[0][2:5] for call in get_status.call_args_list] == [
        ("/setup/eureka_info?params=device_info,name", True, 10),
        ("/setup/eureka_info?params=device_info,name", False, 10),
    ]


def test_get_eureka_info_no_http_fallback(no_cast_eureka_info: MagicMock) -> None:
    """Test that only HTTPS is tried after cast without the HTTP fallback."""
    with (
        patch(
            "pychromecast.dial._get_status",
            side_effect=urllib.error.URLError("no https"),
        ) as get_status,
        pytest.raises(urllib.error.URLError),
    ):
        _get_eureka_info(SERVICES, None, ["multizone"], 30, None, http_fallback=False)
    assert no_cast_eureka_info.call_args[0][3] == 15
    assert [call[0][2:5] for call in get_status.call_args_list] == [
        ("/setup/eureka_info?params=multizone", True, 15),
    ]


def test_get_eureka_info_over_cast(no_cast_eureka_info: MagicMock) -> None:
    """Test that HTTP isn't used when eureka_info is received over cast."""
    no_cast_eureka_info.side_effect = None
    no_cast_eureka_info.return_value = STATUS
    with patch("pychromecast.dial._get_status") as get_status:
        status = _get_eureka_info(SERVICES, None, ["device_info"], 30, None)
    assert status == STATUS
    get_status.assert_not_called()


def test_get_eureka_info_unresolved() -> None:
    """Test that nothing is queried when no service resolves."""
    with (
        patch("pychromecast.dial._get_status") as get_status,
        pytest.raises(urllib.error.URLError),
    ):
        _get_eureka_info(set(), None, ["device_info"], 30, None)
    get_status.assert_not_called()


def _frame(namespace: str, payload: Any) -> bytes:
    """Return a framed message from the platform receiver."""
    msg = CastMessage()
    msg.protocol_version = msg.CASTV2_1_0
    msg.source_id = "receiver-0"
    msg.destination_id = "sender-0"
    msg.namespace = namespace
    if isinstance(payload, bytes):
        msg.payload_type = CastMessage.BINARY
        msg.payload_binary = payload
    else:
        msg.payload_type = CastMessage.STRING
        msg.payload_utf8 = json.dumps(payload)
    return pack(">I", msg.ByteSize()) + msg.SerializeToString()


def _setup_reply(data: Any, request_id: int = 1, code: int = 200) -> bytes:
    return _frame(
        NS_SETUP,
        {
            "type": "eureka_info",
            "request_id": request_id,
            "response_code": code,
            "response_string": "OK" if code == 200 else "Error",
            "data": data,
        },
    )


class FakeCastSocket:
    """A TLS socket of a cast device which sends prepared data in small chunks."""

    def __init__(self, data: bytes) -> None:
        self.received = b""
        self._data = data

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def sendall(self, data: bytes) -> None:
        self.received += data

    def settimeout(self, timeout: float) -> None:
        assert timeout > 0

    def recv(self, size: int) -> bytes:
        chunk, self._data = self._data[: min(size, 7)], self._data[min(size, 7) :]
        return chunk

    def messages(self) -> list[tuple[str, dict]]:
        """Return the namespaces and payloads of the messages sent to the device."""
        messages = []
        data = self.received
        while data:
            (size,) = unpack(">I", data[:4])
            msg = CastMessage()
            msg.ParseFromString(data[4 : 4 + size])
            assert msg.source_id == "sender-0"
            assert msg.destination_id == "receiver-0"
            messages.append((msg.namespace, json.loads(msg.payload_utf8)))
            data = data[4 + size :]
        return messages


def _query_cast(data: bytes) -> tuple[Any, FakeCastSocket]:
    sock = FakeCastSocket(data)
    context = MagicMock()
    context.wrap_socket.return_value = sock
    with patch("socket.create_connection") as create_connection:
        status = _get_eureka_info_cast(
            "192.0.2.1", 8009, ["device_info", "multizone"], 10, context
        )
    assert create_connection.call_args[0] == (("192.0.2.1", 8009), 10)
    return status, sock


def test_get_eureka_info_cast() -> None:
    """Test that eureka_info is requested on the setup namespace."""
    status, sock = _query_cast(
        _frame("urn:x-cast:com.google.cast.receiver", {"type": "RECEIVER_STATUS"})
        + _frame(NS_SETUP, b"binary")
        + _frame(NS_SETUP, ["not", "a", "dict"])
        + _setup_reply({"name": "other request"}, request_id=0)
        + _setup_reply(STATUS)
    )
    assert status == STATUS
    assert sock.messages() == [
        (NS_CONNECTION, connect_message()),
        (
            NS_SETUP,
            {
                "type": "eureka_info",
                "request_id": 1,
                "data": {"params": ["device_info", "multizone"]},
            },
        ),
    ]


@pytest.mark.parametrize(
    ("data", "error"),
    [
        (b"", ConnectionError),
        (_setup_reply(STATUS)[:-1], ConnectionError),
        (pack(">I", 65537), ValueError),
        (_setup_reply(STATUS, code=404), ValueError),
        (_setup_reply(None), ValueError),
        (_setup_reply(["not", "a", "dict"]), ValueError),
        (pack(">I", 20) + b"\xff" * 20, DecodeError),
    ],
)
def test_get_eureka_info_cast_failed(data: bytes, error: type[Exception]) -> None:
    """Test that a closed connection or a bad reply raises."""
    with pytest.raises(error):
        _query_cast(data)


def test_get_eureka_info_cast_timeout() -> None:
    """Test that waiting for the reply times out."""
    with (
        patch("time.monotonic", side_effect=[0, 0, 11]),
        pytest.raises(TimeoutError),
    ):
        _query_cast(_setup_reply(STATUS))


def test_get_multizone_status_over_cast(no_cast_eureka_info: MagicMock) -> None:
    """Test that the groups led by a device are read from eureka_info."""
    no_cast_eureka_info.side_effect = None
    no_cast_eureka_info.return_value = {
        "multizone": {
            "dynamic_groups": [],
            "groups": [
                {
                    "cast_port": 32000,
                    "elected_leader": "self",
                    "name": "Group",
                    "uuid": UUID_STR,
                }
            ],
        }
    }
    status = get_multizone_status("192.0.2.1")
    assert no_cast_eureka_info.call_args[0][:3] == (
        "192.0.2.1",
        8009,
        ["multizone"],
    )
    assert status is not None
    assert not status.dynamic_groups
    assert [(g.uuid, g.host, g.port) for g in status.groups] == [
        (UUID(UUID_STR), "192.0.2.1", 32000)
    ]


def test_get_cast_type_keeps_device_capabilities() -> None:
    """Test that get_cast_type keeps the device capabilities."""
    cast_info = CastInfo(
        {HostServiceInfo("192.0.2.1", 8009)},
        UUID("12345678-1234-1234-1234-123456789abc"),
        "Speaker model",
        "Speaker",
        "192.0.2.1",
        8009,
        None,
        None,
        device_capabilities=CastCapability(0),
    )
    with patch(
        "pychromecast.dial._get_status", side_effect=urllib.error.URLError("down")
    ):
        result = get_cast_type(cast_info)
    assert result.device_capabilities == CastCapability(0)
