"""Tests for pychromecast.dial."""

import urllib.request

import pytest

from pychromecast.dial import (
    _url_decode_hostname,
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
def test_url_decode_hostname(hostname: str, encoded: str) -> None:
    """Test that brackets are removed and zone identifiers decoded."""
    assert _url_decode_hostname(encoded) == hostname


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
