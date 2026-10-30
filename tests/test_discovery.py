"""Tests for pychromecast.discovery."""

from dataclasses import replace
import threading
from unittest.mock import MagicMock, patch
from uuid import UUID

from pychromecast.const import CAST_TYPE_AUDIO
from pychromecast.dial import DeviceStatus
from pychromecast.discovery import HostBrowser, ZeroConfListener
from pychromecast.models import CastInfo, MDNSServiceInfo

HOST = "192.0.2.1"
MAC_ADDRESS = "00:00:5E:00:53:01"
UUID_STR = "12345678-1234-1234-1234-123456789abc"

DEVICE_STATUS = DeviceStatus(
    "Speaker",
    "Chromecast Audio",
    "Google Inc.",
    UUID(UUID_STR),
    CAST_TYPE_AUDIO,
    False,
    MAC_ADDRESS,
    "product",
    "1.2.3",
)


def _poll(browser: HostBrowser, device_status: DeviceStatus) -> None:
    with patch("pychromecast.discovery.get_device_info", return_value=device_status):
        browser._poll_hosts()  # pylint: disable=protected-access


def test_host_browser_copies_details() -> None:
    """Test that polled device details are copied to the cast info."""
    listener = MagicMock()
    devices: dict[UUID, CastInfo] = {}
    browser = HostBrowser(listener, devices, threading.Lock())
    browser.add_hosts([HOST])

    _poll(browser, DEVICE_STATUS)
    cast_info = devices[UUID(UUID_STR)]
    assert cast_info.mac_address == MAC_ADDRESS
    assert cast_info.product_name == "product"
    assert cast_info.cast_build_revision == "1.2.3"
    listener.add_cast.assert_called_once()

    # Unchanged details give no update
    _poll(browser, DEVICE_STATUS)
    listener.update_cast.assert_not_called()

    # Changed details are stored and reported
    _poll(browser, replace(DEVICE_STATUS, cast_build_revision="1.2.4"))
    assert devices[UUID(UUID_STR)].cast_build_revision == "1.2.4"
    listener.update_cast.assert_called_once()


def test_mdns_update_keeps_details() -> None:
    """Test that an mDNS update keeps the polled device details."""
    name = "Speaker._googlecast._tcp.local."
    devices = {
        UUID(UUID_STR): CastInfo(
            {MDNSServiceInfo(name)},
            UUID(UUID_STR),
            "Chromecast Audio",
            "Speaker",
            HOST,
            8009,
            CAST_TYPE_AUDIO,
            "Google Inc.",
            MAC_ADDRESS,
            "product",
            "1.2.3",
        )
    }
    service = MagicMock(port=8009, server=None)
    service.parsed_addresses.return_value = [HOST]
    service.properties = {
        b"fn": b"Renamed",
        b"md": b"Chromecast Audio",
        b"id": UUID_STR.replace("-", "").encode(),
    }
    zconf = MagicMock()
    zconf.get_service_info.return_value = service
    listener = ZeroConfListener(MagicMock(), devices, MagicMock(), threading.Lock())

    listener.update_service(zconf, "_googlecast._tcp.local.", name)

    cast_info = devices[UUID(UUID_STR)]
    assert cast_info.friendly_name == "Renamed"
    assert cast_info.mac_address == MAC_ADDRESS
    assert cast_info.product_name == "product"
    assert cast_info.cast_build_revision == "1.2.3"
