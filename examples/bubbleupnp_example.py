"""
Example on how to use the BubbleUPNP Controller to play an URL.

"""
# pylint: disable=invalid-name

import argparse
import logging
import sys
from time import sleep

import zeroconf

import pychromecast
from pychromecast.controllers.bubbleupnp import BubbleUPNPController


# Change to the friendly name of your Chromecast
CAST_NAME = "Kitchen speaker"

# Change to an audio or video url
MEDIA_URL = "https://c3.toivon.net/toivon/toivon_3?mp=/stream"

parser = argparse.ArgumentParser(
    description="Example on how to use the BubbleUPNP Controller to play an URL."
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
parser.add_argument(
    "--url", help='Media url (default: "%(default)s")', default=MEDIA_URL
)
args = parser.parse_args()

if args.show_debug:
    logging.basicConfig(level=logging.DEBUG)
if args.show_zeroconf_debug:
    print("Zeroconf version: " + zeroconf.__version__)
    logging.getLogger("zeroconf").setLevel(logging.DEBUG)

# pylint: disable=unbalanced-tuple-unpacking
chromecasts, browser = pychromecast.get_listed_chromecasts(
    friendly_names=[args.cast], known_hosts=args.known_host
)
if not chromecasts:
    print(f'No chromecast with name "{args.cast}" discovered')
    sys.exit(1)

cast = list(chromecasts)[0]
# Start socket client's worker thread and wait for initial status update
cast.wait()
print(f'Found chromecast with name "{args.cast}", attempting to play "{args.url}"')
bubbleupnp = BubbleUPNPController()
cast.register_handler(bubbleupnp)
bubbleupnp.launch()
bubbleupnp.play_media(args.url, "audio/mp3", stream_type="LIVE")

sleep(10)

browser.stop_discovery()
