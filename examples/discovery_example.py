"""
Example that shows how to receive updates on discovered chromecasts.
"""
# pylint: disable=invalid-name

import argparse
import logging
import time

import zeroconf

import pychromecast

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
    "--show-zeroconf-debug", help="Enable zeroconf debug log", action="store_true"
)
args = parser.parse_args()

if args.show_debug:
    logging.basicConfig(level=logging.DEBUG)
if args.show_zeroconf_debug:
    print("Zeroconf version: " + zeroconf.__version__)
    logging.getLogger("zeroconf").setLevel(logging.DEBUG)


def list_devices():
    """Print a list of known devices."""
    print("Currently known cast devices:")
    for uuid, service in browser.services.items():
        print("  {} {}".format(uuid, service))


class MyCastListener(pychromecast.discovery.AbstractCastListener):
    """Listener for discovering chromecasts."""

    def add_cast(self, uuid, _service):
        """Called when a new cast has beeen discovered."""
        print("Found cast device with UUID {}".format(uuid))
        list_devices()

    def remove_cast(self, uuid, _service, cast_info):
        """Called when a cast has beeen lost (MDNS info expired or host down)."""
        print("Lost cast device with UUID {} {}".format(uuid, cast_info))
        list_devices()

    def update_cast(self, uuid, _service):
        """Called when a cast has beeen updated (MDNS info renewed or changed)."""
        print("Updated cast device with UUID {}".format(uuid))
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
