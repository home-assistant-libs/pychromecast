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
    for uuid, service in listener.services.items():
        print("  {} {}".format(uuid, service))


def add_callback(uuid, _name):
    """Called when a new cast has beeen discovered."""
    print("Found mDNS service for cast device {}".format(uuid))
    list_devices()


def remove_callback(uuid, _name, service):
    """Called when a cast has beeen lost (MDNS info expired)."""
    print("Lost mDNS service for cast device {} {}".format(uuid, service))
    list_devices()


def update_callback(uuid, _name):
    """Called when a cast has beeen updated (MDNS info renewed or changed)."""
    print("Updated mDNS service for cast device {}".format(uuid))
    list_devices()


listener = pychromecast.CastListener(add_callback, remove_callback, update_callback)
zconf = zeroconf.Zeroconf()
browser = pychromecast.discovery.start_discovery(listener, zconf)

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass

pychromecast.stop_discovery(browser)
