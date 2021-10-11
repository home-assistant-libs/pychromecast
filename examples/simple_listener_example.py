"""
Example showing how to create a simple Chromecast event listener for
device and media status events
"""
# pylint: disable=invalid-name

import argparse
import logging
import sys
import time
import zeroconf

import pychromecast
from pychromecast.controllers.media import MediaStatusListener
from pychromecast.controllers.receiver import CastStatusListener

# Change to the friendly name of your Chromecast
CAST_NAME = "Living Room Speaker"


class MyCastStatusListener(CastStatusListener):
    """Cast status listener"""

    def __init__(self, name, cast):
        self.name = name
        self.cast = cast

    def new_cast_status(self, status):
        print("[", time.ctime(), " - ", self.name, "] status chromecast change:")
        print(status)


class MyMediaStatusListener(MediaStatusListener):
    """Status media listener"""

    def __init__(self, name, cast):
        self.name = name
        self.cast = cast

    def new_media_status(self, status):
        print("[", time.ctime(), " - ", self.name, "] status media change:")
        print(status)


parser = argparse.ArgumentParser(
    description="Example on how to create a simple Chromecast event listener."
)
parser.add_argument(
    "--cast", help='Name of cast device (default: "%(default)s")', default=CAST_NAME
)
parser.add_argument(
    "--known-host",
    help="Add known host (IP), can be used multiple times",
    action="append",
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

chromecasts, browser = pychromecast.get_listed_chromecasts(
    friendly_names=[args.cast], known_hosts=args.known_host
)
if not chromecasts:
    print(f'No chromecast with name "{args.cast}" discovered')
    sys.exit(1)

chromecast = chromecasts[0]
# Start socket client's worker thread and wait for initial status update
chromecast.wait()

listenerCast = MyCastStatusListener(chromecast.name, chromecast)
chromecast.register_status_listener(listenerCast)

listenerMedia = MyMediaStatusListener(chromecast.name, chromecast)
chromecast.media_controller.register_status_listener(listenerMedia)

input("Listening for Chromecast events...\n\n")

# Shut down discovery
browser.stop_discovery()
