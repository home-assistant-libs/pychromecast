"""Basic tests for pychromecast."""

import pychromecast


def test_import() -> None:
    """Test that the package can be imported."""
    assert pychromecast.Chromecast
