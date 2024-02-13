"""
Example that shows how to receive updates on discovered chromecasts.
"""
# pylint: disable=invalid-name

import argparse
import logging
import sys
import time
from uuid import UUID

import zeroconf

import pychromecast
from pychromecast import CastInfo

# Enable deprecation warnings etc.
if not sys.warnoptions:
    import warnings

    warnings.simplefilter("default")

parser = argparse.ArgumentParser(
    description="Example on how to receive updates on discovered chromecasts."
)
parser.add_argument(
    "--known-host",
    help="Add known host (IP), can be used multiple times",
    action="append",
)
parser.add_argument(
    "--force-zeroconf",
    help="Zeroconf will be used even if --known-host is present",
    action="store_true",
)
parser.add_argument("--show-debug", help="Enable debug log", action="store_true")
parser.add_argument(
    "--show-discovery-debug", help="Enable discovery debug log", action="store_true"
)
parser.add_argument(
    "--show-zeroconf-debug", help="Enable zeroconf debug log", action="store_true"
)
parser.add_argument(
    "--verbose", help="Full display of discovered devices", action="store_true"
)
args = parser.parse_args()

if args.show_debug:
    fmt = "%(asctime)s %(levelname)s (%(threadName)s) [%(name)s] %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    logging.basicConfig(format=fmt, datefmt=datefmt, level=logging.DEBUG)
    logging.getLogger("pychromecast.dial").setLevel(logging.INFO)
    logging.getLogger("pychromecast.discovery").setLevel(logging.INFO)
if args.show_discovery_debug:
    logging.getLogger("pychromecast.dial").setLevel(logging.DEBUG)
    logging.getLogger("pychromecast.discovery").setLevel(logging.DEBUG)
if args.show_zeroconf_debug:
    print("Zeroconf version: " + zeroconf.__version__)
    logging.getLogger("zeroconf").setLevel(logging.DEBUG)


def list_devices() -> None:
    """Print a list of known devices."""
    print("Currently known cast devices:")
    for service in browser.services.values():
        print(
            f"  '{service.friendly_name}' ({service.model_name}) @ {service.host}:{service.port} uuid: {service.uuid}"
        )
        if args.verbose:
            print(f"  service: {service}")


class MyCastListener(pychromecast.discovery.AbstractCastListener):
    """Listener for discovering chromecasts."""

    def add_cast(self, uuid: UUID, service: str) -> None:
        """Called when a new cast has beeen discovered."""
        print(
            f"Found cast device '{browser.services[uuid].friendly_name}' with UUID {uuid}"
        )
        list_devices()

    def remove_cast(self, uuid: UUID, service: str, cast_info: CastInfo) -> None:
        """Called when a cast has beeen lost (MDNS info expired or host down)."""
        print(f"Lost cast device '{cast_info.friendly_name}' with UUID {uuid}")
        list_devices()

    def update_cast(self, uuid: UUID, service: str) -> None:
        """Called when a cast has beeen updated (MDNS info renewed or changed)."""
        print(
            f"Updated cast device '{browser.services[uuid].friendly_name}' with UUID {uuid}"
        )
        list_devices()


if args.known_host and not args.force_zeroconf:
    zconf = None
else:
    zconf = zeroconf.Zeroconf()
browser = pychromecast.discovery.CastBrowser(MyCastListener(), zconf, args.known_host)
browser.start_discovery()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass

# Shut down discovery
browser.stop_discovery()
