"""
Example on how to use the NRK Radio Controller
"""
# pylint: disable=invalid-name

import argparse
import sys
from time import sleep

import pychromecast
from pychromecast import quick_play

from .common import add_log_arguments, configure_logging

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
add_log_arguments(parser)
parser.add_argument(
    "--media_id", help='MediaID (default: "%(default)s")', default=MEDIA_ID
)
args = parser.parse_args()

configure_logging(args)

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
