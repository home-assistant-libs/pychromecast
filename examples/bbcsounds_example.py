"""
Example on how to use the BBC iPlayer Controller
"""
# pylint: disable=invalid-name

import argparse
import logging
import sys
from time import sleep
import json

import zeroconf
import pychromecast
from pychromecast import quick_play

# Change to the name of your Chromecast
CAST_NAME = "Lounge Video"

# Media ID can be found in the URL
# e.g. https://www.bbc.co.uk/sounds/live:bbc_radio_one
MEDIA_ID = "bbc_radio_one"
IS_LIVE = True
METADATA = {
    "metadatatype": 0,
    "title": "Radio 1",
    "images": [
        {
            "url": "https://sounds.files.bbci.co.uk/2.3.0/networks/bbc_radio_one/background_1280x720.png"
        }
    ],
}

parser = argparse.ArgumentParser(
    description="Example on how to use the BBC Sounds Controller to play an media stream."
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
parser.add_argument(
    "--metadata", help='Metadata (default: "%(default)s")', default=json.dumps(METADATA)
)
parser.add_argument(
    "--is_live",
    help="Show 'live' and no current/end timestamps on UI",
    action="store_true",
    default=IS_LIVE,
)
args = parser.parse_args()

app_name = "bbcsounds"
app_data = {
    "media_id": args.media_id,
    "is_live": args.is_live,
    "metadata": json.loads(args.metadata),
}

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

quick_play.quick_play(cast, app_name, app_data)

sleep(10)

browser.stop_discovery()
