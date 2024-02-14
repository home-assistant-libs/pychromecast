"""
Example on how to use the BubbleUPNP Controller to play an URL.

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
CAST_NAME = "Kitchen speaker"

# Change to an audio or video url
MEDIA_URL = (
    "http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"
)
MEDIA_TYPE = "video/mp4"

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
add_log_arguments(parser)
parser.add_argument(
    "--url", help='Media url (default: "%(default)s")', default=MEDIA_URL
)
parser.add_argument(
    "--media-type", help='Media type (default: "%(default)s")', default=MEDIA_TYPE
)
args = parser.parse_args()

configure_logging(args)

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

app_name = "bubbleupnp"
app_data = {
    "media_id": args.url,
    "media_type": args.media_type,
    "stream_type": "LIVE",
}
quick_play.quick_play(cast, app_name, app_data)

sleep(10)

browser.stop_discovery()
