"""
Example on how to use the BBC Sounds Controller
"""

# pylint: disable=invalid-name

import argparse
import sys
from time import sleep
import json

import pychromecast
from pychromecast import quick_play

from .common import add_log_arguments, configure_logging

# Enable deprecation warnings etc.
if not sys.warnoptions:
    import warnings

    warnings.simplefilter("default")

# Change to the name of your Chromecast
CAST_NAME = "Lounge Video"

# Note:
# Media ID for live programs can be found in the URL
# e.g. for https://www.bbc.co.uk/sounds/play/live:bbc_radio_one, the media ID is bbc_radio_one
# Media ID for non-live programs is NOT the 8 digit alpha-numeric in the URL
# it can be found by right clicking the playing video on the web interface
# e.g. https://www.bbc.co.uk/sounds/play/m0015vch shows:
# "96kbps | dash (mf_akamai_nonbidi_dash_https)
#  m0015vcg", the media ID is m0015vcg
MEDIA_ID = "bbc_radio_one"
DEFAULT_MEDIA_ID_IS_LIVE = True
IS_LIVE = False
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
add_log_arguments(parser)
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

# Set live if playing the default
if args.media_id == MEDIA_ID:
    args.is_live = DEFAULT_MEDIA_ID_IS_LIVE

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

app_name = "bbcsounds"
app_data = {
    "media_id": args.media_id,
    "is_live": args.is_live,
    "metadata": json.loads(args.metadata),
}
quick_play.quick_play(cast, app_name, app_data)

# If debugging, sleep after running so we can see any error messages.
if args.show_debug:
    sleep(10)

browser.stop_discovery()
