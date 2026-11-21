"""Basic tests for pychromecast."""

from unittest.mock import MagicMock, patch

import pychromecast


def test_import() -> None:
    """Test that the package can be imported."""
    assert pychromecast.Chromecast


@patch("pychromecast.discovery.zeroconf.ServiceBrowser")
@patch("pychromecast.create_zeroconf")
def test_get_chromecasts_closes_created_zeroconf(
    create_zeroconf: MagicMock, service_browser: MagicMock
) -> None:
    """Test that stopping discovery closes a zeroconf instance pychromecast made."""
    browser = pychromecast.get_chromecasts(blocking=False)
    browser.stop_discovery()

    create_zeroconf.return_value.close.assert_called_once()
