"""Basic tests for pychromecast."""

from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

import pychromecast
from pychromecast.models import CastInfo, HostServiceInfo

TEST_UUID = UUID("42feced1-d942-3823-2fba-92623e2682f3")


def test_import() -> None:
    """Test that the package can be imported."""
    assert pychromecast.Chromecast


def _cast_info() -> CastInfo:
    return CastInfo(
        {HostServiceInfo("192.0.2.1", 8009)},
        TEST_UUID,
        "Chromecast Audio",
        "Kitchen",
        "192.0.2.1",
        8009,
        "audio",
        "Google Inc.",
    )


@pytest.mark.parametrize(
    ("kwargs", "device_auth"),
    [({}, True), ({"device_auth": True}, True), ({"device_auth": False}, False)],
)
def test_chromecast_device_auth(kwargs: dict[str, Any], device_auth: bool) -> None:
    """Test Chromecast passes the device auth options to the socket client."""
    with patch("pychromecast.socket_client.SocketClient") as socket_client:
        pychromecast.Chromecast(_cast_info(), **kwargs)
    assert socket_client.call_args.kwargs["device_auth"] is device_auth
    assert socket_client.call_args.kwargs["expected_uuid"] == TEST_UUID


def test_chromecast_device_auth_result() -> None:
    """Test Chromecast exposes the socket client's device auth result."""
    with patch("pychromecast.socket_client.SocketClient") as socket_client:
        cast = pychromecast.Chromecast(_cast_info())
    assert cast.device_auth_result is socket_client.return_value.device_auth_result


@pytest.mark.parametrize("device_auth", [True, False])
def test_get_chromecast_from_cast_info(device_auth: bool) -> None:
    """Test get_chromecast_from_cast_info passes device_auth."""
    cast_info = _cast_info()
    with patch("pychromecast.Chromecast") as chromecast:
        pychromecast.get_chromecast_from_cast_info(
            cast_info, None, device_auth=device_auth
        )
    assert chromecast.call_args.kwargs["device_auth"] is device_auth
    assert chromecast.call_args.kwargs["cast_info"] is cast_info


@pytest.mark.parametrize("device_auth", [True, False])
def test_get_chromecast_from_host(device_auth: bool) -> None:
    """Test get_chromecast_from_host passes device_auth and the UUID."""
    with patch("pychromecast.Chromecast") as chromecast:
        pychromecast.get_chromecast_from_host(
            ("192.0.2.1", 8009, TEST_UUID, "Chromecast Audio", "Kitchen"),
            device_auth=device_auth,
        )
    assert chromecast.call_args.kwargs["device_auth"] is device_auth
    assert chromecast.call_args.kwargs["cast_info"].uuid == TEST_UUID


def test_get_chromecast_from_host_default() -> None:
    """Test device authentication is enabled by default."""
    with patch("pychromecast.Chromecast") as chromecast:
        pychromecast.get_chromecast_from_host(
            ("192.0.2.1", 8009, TEST_UUID, "Chromecast Audio", "Kitchen")
        )
    assert chromecast.call_args.kwargs["device_auth"] is True


@pytest.mark.parametrize("device_auth", [True, False])
def test_get_chromecasts_blocking(device_auth: bool) -> None:
    """Test blocking get_chromecasts passes device_auth."""
    cast_info = _cast_info()
    browser = MagicMock()
    with (
        patch("pychromecast.discover_chromecasts", return_value=([cast_info], browser)),
        patch("pychromecast.get_chromecast_from_cast_info") as from_cast_info,
    ):
        pychromecast.get_chromecasts(device_auth=device_auth)
    assert from_cast_info.call_args.kwargs["device_auth"] is device_auth


def _capture_listener(browser_class: MagicMock) -> Any:
    """Return the listener passed to the mocked CastBrowser."""
    listener = browser_class.call_args.args[0]
    browser_class.return_value.devices = {TEST_UUID: _cast_info()}
    return listener


@pytest.mark.parametrize("device_auth", [True, False])
def test_get_chromecasts_non_blocking(device_auth: bool) -> None:
    """Test non-blocking get_chromecasts passes device_auth."""
    with (
        patch("pychromecast.CastBrowser") as browser_class,
        patch("pychromecast.get_chromecast_from_cast_info") as from_cast_info,
    ):
        pychromecast.get_chromecasts(
            blocking=False,
            callback=lambda _cast: None,
            zeroconf_instance=MagicMock(),
            device_auth=device_auth,
        )
        _capture_listener(browser_class).add_cast(TEST_UUID, "service")
    assert from_cast_info.call_args.kwargs["device_auth"] is device_auth


@pytest.mark.parametrize("device_auth", [True, False])
def test_get_listed_chromecasts(device_auth: bool) -> None:
    """Test get_listed_chromecasts passes device_auth."""
    listeners: list[Any] = []

    def start_discovery() -> None:
        listener = _capture_listener(browser_class)
        listeners.append(listener)
        listener.add_cast(TEST_UUID, "service")

    with (
        patch("pychromecast.CastBrowser") as browser_class,
        patch("pychromecast.get_chromecast_from_cast_info") as from_cast_info,
    ):
        browser_class.return_value.start_discovery.side_effect = start_discovery
        pychromecast.get_listed_chromecasts(
            uuids=[TEST_UUID],
            discovery_timeout=1,
            zeroconf_instance=MagicMock(),
            device_auth=device_auth,
        )
    assert listeners
    assert from_cast_info.call_args.kwargs["device_auth"] is device_auth
