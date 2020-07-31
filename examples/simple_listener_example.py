"""
Example showing how to create a simple Chromecast event listener for
device and media status events
"""

import argparse
import logging
import sys
import time

import pychromecast
import zeroconf

# Change to the friendly name of your Chromecast
CAST_NAME = "Living Room Speaker"


class StatusListener:
    def __init__(self, name, cast):
        self.name = name
        self.cast = cast

    def new_cast_status(self, status):
        print("[", time.ctime(), " - ", self.name, "] status chromecast change:")
        print(status)


class StatusMediaListener:
    def __init__(self, name, cast):
        self.name = name
        self.cast = cast

    def new_media_status(self, status):
        print("[", time.ctime(), " - ", self.name, "] status media change:")
        print(status)


parser = argparse.ArgumentParser(
    description="Example on how to create a simple Chromecast event listener."
)
parser.add_argument("--show-debug", help="Enable debug log", action="store_true")
parser.add_argument("--show-zeroconf-debug", help="Enable zeroconf debug log", action="store_true")
parser.add_argument(
    "--cast", help='Name of cast device (default: "%(default)s")', default=CAST_NAME
)
args = parser.parse_args()

if args.show_debug:
    logging.basicConfig(level=logging.DEBUG)
if args.show_zeroconf_debug:
    print("Zeroconf version: " + zeroconf.__version__)
    logging.getLogger("zeroconf").setLevel(logging.DEBUG)

chromecasts, browser  = pychromecast.get_listed_chromecasts(friendly_names=[args.cast])
if not chromecasts:
    print('No chromecast with name "{}" discovered'.format(args.cast))
    sys.exit(1)

chromecast = chromecasts[0]
# Start socket client's worker thread and wait for initial status update
chromecast.wait()

listenerCast = StatusListener(chromecast.name, chromecast)
chromecast.register_status_listener(listenerCast)

listenerMedia = StatusMediaListener(chromecast.name, chromecast)
chromecast.media_controller.register_status_listener(listenerMedia)

input("Listening for Chromecast events...\n\n")

# Shut down discovery
pychromecast.discovery.stop_discovery(browser)
