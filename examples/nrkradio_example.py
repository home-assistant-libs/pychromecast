"""
Example on how to use the NRK Radio Controller
"""
# pylint: disable=invalid-name

import argparse
import logging
import sys
from time import sleep

import zeroconf

import pychromecast
from pychromecast import quick_play

# Enable deprecation warnings etc.
if not sys.warnoptions:
    import warnings

    warnings.simplefilter("default")

# Change to the friendly name of your Chromecast
CAST_NAME = "Living Room"

# Note: Media ID can be found in the URL, e.g:
# For the live channel https://radio.nrk.no/direkte/p1, the media ID is p1
# For the podcast https://radio.nrk.no/podkast/tazte_priv/l_8457deb0-4f2c-4ef3-97de-b04f2c6ef314,
# the media ID is l_8457deb0-4f2c-4ef3-97de-b04f2c6ef314
# For the on-demand program https://radio.nrk.no/serie/radiodokumentaren/sesong/201011/MDUP01004510,
# the media id is MDUP01004510
MEDIA_ID = "l_8457deb0-4f2c-4ef3-97de-b04f2c6ef314"

parser = argparse.ArgumentParser(
    description="Example on how to use the NRK Radio Controller to play a media stream."
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
    "--show-discovery-debug", help="Enable discovery debug log", action="store_true"
)
parser.add_argument(
    "--show-zeroconf-debug", help="Enable zeroconf debug log", action="store_true"
)
parser.add_argument(
    "--media_id", help='MediaID (default: "%(default)s")', default=MEDIA_ID
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

app_name = "nrkradio"
app_data = {
    "media_id": args.media_id,
}
quick_play.quick_play(cast, app_name, app_data)

sleep(10)

browser.stop_discovery()
