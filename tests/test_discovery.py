"""Tests for pychromecast.discovery."""

from dataclasses import replace
import threading
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from pychromecast.const import (
    CAST_TYPE_AUDIO,
    CAST_TYPE_CHROMECAST,
    CAST_TYPE_GROUP,
    CastCapability,
)
from pychromecast.dial import DeviceStatus
from pychromecast.discovery import HostBrowser, ZeroConfListener
from pychromecast.models import CastInfo, MDNSServiceInfo

HOST = "192.0.2.1"
MAC_ADDRESS = "00:00:5E:00:53:01"
NAME = "Speaker._googlecast._tcp.local."
UUID_STR = "12345678-1234-1234-1234-123456789abc"
# Audio out and an unknown bit
DEVICE_CAPABILITIES = CastCapability.AUDIO_OUT | CastCapability(1 << 16)


def _mdns_update(
    devices: dict[UUID, CastInfo],
    ca: bytes | None,
    model: bytes = b"Speaker model",
    port: int = 8009,
) -> None:
    service = MagicMock(port=port, server=None)
    service.parsed_addresses.return_value = [HOST]
    service.properties = {
        b"fn": b"Speaker",
        b"md": model,
        b"id": UUID_STR.replace("-", "").encode(),
    }
    if ca is not None:
        service.properties[b"ca"] = ca
    zconf = MagicMock()
    zconf.get_service_info.return_value = service
    listener = ZeroConfListener(MagicMock(), devices, MagicMock(), threading.Lock())
    listener.update_service(zconf, "_googlecast._tcp.local.", NAME)


@pytest.mark.parametrize(
    ("ca", "device_capabilities"),
    [
        (b"65540", DEVICE_CAPABILITIES),
        (b"5", CastCapability.VIDEO_OUT | CastCapability.AUDIO_OUT),
        (b"0", CastCapability(0)),
        (None, None),
        (b"", None),
        (b"-1", None),
        (b"0x5", None),
    ],
)
def test_mdns_parses_device_capabilities(
    ca: bytes | None, device_capabilities: CastCapability | None
) -> None:
    """Test that the capabilities are parsed from the ca value of the TXT record."""
    devices: dict[UUID, CastInfo] = {}

    _mdns_update(devices, ca)

    assert devices[UUID(UUID_STR)].device_capabilities == device_capabilities


@pytest.mark.parametrize(
    ("port", "model", "ca", "cast_type", "manufacturer"),
    [
        (8009, b"Speaker model", b"4", CAST_TYPE_AUDIO, None),
        (8009, b"Speaker model", b"5", CAST_TYPE_CHROMECAST, None),
        (8009, b"Speaker model", b"36", CAST_TYPE_GROUP, None),
        # No output, or no capabilities
        (8009, b"Speaker model", b"0", None, None),
        (8009, b"Speaker model", None, None, None),
        # A known model decides over the capabilities
        (8009, b"Chromecast Audio", b"5", CAST_TYPE_AUDIO, "Google Inc."),
        # Another port is a group
        (32000, b"Google Cast Group", b"5", CAST_TYPE_GROUP, "Google Inc."),
    ],
)
def test_mdns_cast_type_from_device_capabilities(
    port: int,
    model: bytes,
    ca: bytes | None,
    cast_type: str | None,
    manufacturer: str | None,
) -> None:
    """Test that the capabilities give the cast type of an unknown model."""
    devices: dict[UUID, CastInfo] = {}

    _mdns_update(devices, ca, model, port)

    cast_info = devices[UUID(UUID_STR)]
    assert cast_info.cast_type == cast_type
    assert cast_info.manufacturer == manufacturer


def test_mdns_update_device_capabilities() -> None:
    """Test that an mDNS update stores the new capabilities."""
    devices: dict[UUID, CastInfo] = {}
    _mdns_update(devices, b"4")

    _mdns_update(devices, b"65540")

    assert devices[UUID(UUID_STR)].device_capabilities == DEVICE_CAPABILITIES


def test_host_browser_keeps_device_capabilities() -> None:
    """Test that polling a host keeps the capabilities found by mDNS."""
    devices = {
        UUID(UUID_STR): CastInfo(
            {MDNSServiceInfo(NAME)},
            UUID(UUID_STR),
            "Speaker model",
            "Speaker",
            HOST,
            8009,
            CAST_TYPE_AUDIO,
            "Google Inc.",
            device_capabilities=DEVICE_CAPABILITIES,
        )
    }
    browser = HostBrowser(MagicMock(), devices, threading.Lock())
    browser.add_hosts([HOST])
    device_status = DeviceStatus(
        "Renamed",
        "Speaker model",
        "Google Inc.",
        UUID(UUID_STR),
        CAST_TYPE_AUDIO,
        False,
    )

    with patch("pychromecast.discovery.get_device_info", return_value=device_status):
        browser._poll_hosts()  # pylint: disable=protected-access

    cast_info = devices[UUID(UUID_STR)]
    assert cast_info.friendly_name == "Renamed"
    assert cast_info.device_capabilities == DEVICE_CAPABILITIES


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
            mac_address=MAC_ADDRESS,
            product_name="product",
            cast_build_revision="1.2.3",
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
