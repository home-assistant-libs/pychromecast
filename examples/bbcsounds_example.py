"""
Example on how to use the BBC iPlayer Controller
"""
# pylint: disable=invalid-name

import argparse
import logging
import sys
from time import sleep

import zeroconf
import pychromecast
from pychromecast.controllers.bbcsounds import BbcSoundsController

# Change to the name of your Chromecast
CAST_NAME = "Lounge Video"

# Media ID can be found in the URL
# e.g. https://www.bbc.co.uk/sounds/live:bbc_radio_one
MEDIA_ID = 'bbc_radio_one'
METADATA = {
	"metadata": {
		"metadatatype": 0,
		"title": "Radio 1",
		"images": [{
			"url": "https://sounds.files.bbci.co.uk/2.3.0/networks/bbc_radio_one/background_1280x720.png"
		}]
	}
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
    "--url", help='MediaID (default: "%(default)s")', default=MEDIA_ID
)
parser.add_argument(
    "--metadata", help='Metadata (default: "%(default)s")', default=METADATA
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
    print('No chromecast with name "{}" discovered'.format(args.cast))
    sys.exit(1)

cast = chromecasts[0]
# Start socket client's worker thread and wait for initial status update
cast.wait()
print(
    'Found chromecast with name "{}", attempting to play "{}"'.format(
        args.cast, args.url
    )
)

bbcsounds = BbcSoundsController()
cast.register_handler(bbcsounds)
bbcsounds.launch()
bbcsounds.play_media(MEDIA_ID, False, **METADATA)

sleep(10)

browser.stop_discovery()