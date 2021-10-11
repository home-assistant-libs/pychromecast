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

# Note: Media ID is NOT the 8 digit alpha-numeric in the URL
# it can be found by right clicking the playing video on the web interface
# e.g. https://www.bbc.co.uk/iplayer/episode/b09w7fd9/bitz-bob-series-1-1-castle-makeover shows:
# "2908kbps | dash (mf_cloudfront_dash_https)
#  b09w70r2 | 960x540"
MEDIA_ID = "b09w70r2"
IS_LIVE = False
METADATA = {
    "metadatatype": 0,
    "title": "Bitz & Bob",
    "subtitle": "Castle Makeover",
    "images": [{"url": "https://ichef.bbci.co.uk/images/ic/1280x720/p07j4m3r.jpg"}],
}

parser = argparse.ArgumentParser(
    description="Example on how to use the BBC iPlayer Controller to play an media stream."
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

app_name = "bbciplayer"
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
