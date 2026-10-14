"""Tests for pychromecast.dial."""

import urllib.request

import pytest

from pychromecast.dial import (
    _get_group_info,
    _url_encode_hostname,
    _url_host_header,
)

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
    """Test that the leader host is extracted from the elected leader."""
    group = {"elected_leader": f"{encoded}:8009"}
    assert _get_group_info("10.0.0.1", group).host == hostname


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
