"""Tests for pychromecast.dial."""

from dataclasses import replace
from typing import Any
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from pychromecast.const import CAST_TYPE_AUDIO, CAST_TYPE_CHROMECAST, CAST_TYPE_GROUP
from pychromecast.dial import (
    _get_eureka_info,
    _get_group_info,
    _url_encode_hostname,
    _url_host_header,
    get_cast_type,
    get_device_info,
    get_host_from_zc_service_info,
)
from pychromecast.models import CastInfo, HostServiceInfo

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
    group = {"elected_leader": f"{encoded}:8009"}
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
    group = {"elected_leader": elected_leader}
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
    group = {"elected_leader": elected_leader}
    assert _get_group_info("10.0.0.1", group).host == leader_host


def test_get_group_info_elected_leader_self() -> None:
    """Test that a self elected leader uses the host and cast port."""
    group = {"elected_leader": "self", "cast_port": 32187}
    info = _get_group_info("10.0.0.1", group)
    assert (info.host, info.port) == ("10.0.0.1", 32187)


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


def test_get_eureka_info_falls_back_to_http() -> None:
    """Test that eureka_info is requested over HTTP if HTTPS fails."""
    with patch(
        "pychromecast.dial._get_status",
        side_effect=[urllib.error.URLError("no https"), ("192.0.2.1", STATUS)],
    ) as get_status:
        status = _get_eureka_info(set(), None, ["device_info", "name"], 30, None)
    assert status == STATUS
    assert [call[0][2:5] for call in get_status.call_args_list] == [
        ("/setup/eureka_info?params=device_info,name", True, 15),
        ("/setup/eureka_info?params=device_info,name", False, 15),
    ]
