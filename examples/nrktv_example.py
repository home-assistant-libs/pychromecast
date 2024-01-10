"""
Example on how to use the NRK TV Controller
"""
# pylint: disable=invalid-name

import argparse
import logging
import sys
from time import sleep

import zeroconf

import pychromecast
from pychromecast import quick_play

# Change to the friendly name of your Chromecast
CAST_NAME = "Living Room"

# Note: Media ID for live programs can be found in the URL
# e.g. for https://tv.nrk.no/direkte/nrk1, the media ID is nrk1
# Media ID for non-live programs can be found by clicking the share button
# e.g. https://tv.nrk.no/serie/uti-vaar-hage/sesong/2/episode/2 shows:
# "https://tv.nrk.no/se?v=OUHA43000207", the media ID is OUHA43000207
MEDIA_ID = "OUHA43000207"

parser = argparse.ArgumentParser(
    description="Example on how to use the NRK TV Controller to play a media stream."
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
    "--media_id", help='MediaID (default: "%(default)s")', default=MEDIA_ID
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

cast = chromecasts[0]
# Start socket client's worker thread and wait for initial status update
cast.wait()
print(f'Found chromecast with name "{args.cast}", attempting to play "{args.media_id}"')

app_name = "nrktv"
app_data = {
    "media_id": args.media_id,
}
quick_play.quick_play(cast, app_name, app_data)

sleep(10)

browser.stop_discovery()
