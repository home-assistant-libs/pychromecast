"""Tests for pychromecast.discovery."""

import threading
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from pychromecast.dial import DeviceStatus
from pychromecast.discovery import CastBrowser, HostBrowser, ZeroConfListener
from pychromecast.models import IpVersion

HOSTS = ["192.168.1.2", "fe80::1%2", "2001:db8::1", "chromecast.local"]


@pytest.mark.parametrize(
    ("ip_version", "expected"),
    [
        (None, HOSTS),
        (4, ["192.168.1.2", "chromecast.local"]),
        (6, ["fe80::1%2", "2001:db8::1", "chromecast.local"]),
    ],
)
def test_host_browser_add_hosts_ip_version(
    ip_version: IpVersion | None, expected: list[str]
) -> None:
    """Test that hosts of another IP version are not polled."""
    host_browser = HostBrowser(MagicMock(), {}, threading.Lock(), ip_version)
    host_browser.add_hosts(HOSTS)
    assert list(host_browser._known_hosts) == expected  # pylint: disable=protected-access


def test_cast_browser_ip_version() -> None:
    """Test that the cast browser filters known hosts on IP version."""
    browser = CastBrowser(MagicMock(), None, HOSTS, ip_version=6)
    # pylint: disable-next=protected-access
    assert list(browser.host_browser._known_hosts) == [
        "fe80::1%2",
        "2001:db8::1",
        "chromecast.local",
    ]


@pytest.mark.parametrize(
    ("ip_version", "expected"),
    [(None, "192.168.1.2"), (4, "192.168.1.2"), (6, "fe80::1%2")],
)
def test_zeroconf_listener_host_ip_version(
    ip_version: IpVersion | None, expected: str
) -> None:
    """Test that the host from mDNS passed on for polling is of the IP version."""
    service = MagicMock()
    service.port = 8009
    service.parsed_scoped_addresses.return_value = ["192.168.1.2", "fe80::1%2"]
    service.properties = {}
    zconf = MagicMock()
    zconf.get_service_info.return_value = service
    host_browser = MagicMock()
    listener = ZeroConfListener(
        MagicMock(), {}, host_browser, threading.Lock(), ip_version
    )

    listener.add_service(zconf, "_googlecast._tcp.local.", "Chromecast")

    host_browser.add_hosts.assert_called_once_with([expected])


def test_host_browser_poll_ip_version() -> None:
    """Test that polling uses and propagates the IP version."""
    host_browser = HostBrowser(MagicMock(), {}, threading.Lock(), 6)
    host_browser.add_hosts(["fe80::1%2"])
    device_status = DeviceStatus(
        "Speaker",
        "Google Home",
        "Google Inc.",
        UUID("12345678123456781234567812345678"),
        "audio",
        True,
    )
    multizone_status = MagicMock()
    multizone_status.dynamic_groups = []
    multizone_status.groups = [
        MagicMock(host="192.168.1.3"),
        MagicMock(host="fe80::3%2"),
    ]

    calls: list[tuple[str, dict[str, Any]]] = []

    def get_device_info(_host: str, **kwargs: Any) -> DeviceStatus:
        calls.append(("device", kwargs))
        return device_status

    def get_multizone_status(_host: str, **kwargs: Any) -> Any:
        calls.append(("multizone", kwargs))
        return multizone_status

    with (
        patch("pychromecast.discovery.get_device_info", get_device_info),
        patch("pychromecast.discovery.get_multizone_status", get_multizone_status),
        patch.object(host_browser, "_update_devices"),
    ):
        host_browser._poll_hosts()  # pylint: disable=protected-access

    assert [(kind, kwargs["ip_version"]) for kind, kwargs in calls] == [
        ("device", 6),
        ("multizone", 6),
    ]
    # The IPv4 group leader is not added for polling
    assert list(host_browser._known_hosts) == ["fe80::1%2", "fe80::3%2"]  # pylint: disable=protected-access
