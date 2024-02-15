"""
Example changing the playback rate.

"""

# pylint: disable=invalid-name

import argparse
import sys
import time

import pychromecast

from .common import add_log_arguments, configure_logging

# Enable deprecation warnings etc.
if not sys.warnoptions:
    import warnings

    warnings.simplefilter("default")

# Change to the friendly name of your Chromecast
CAST_NAME = "Living Room"

# Change to an audio or video url
MEDIA_URL = (
    "http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"
)

parser = argparse.ArgumentParser(
    description="Example on how to use the Media Controller."
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

print(f'Playing media "{args.url}"')
cast.play_media(args.url, "video/mp4")

print("Waiting for media session to be active")
cast.media_controller.block_until_active()

SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2]
for speed in SPEEDS:
    time.sleep(10)
    print(f"Setting playback rate to {speed}")
    cast.media_controller.set_playback_rate(speed)

# Shut down discovery
browser.stop_discovery()
