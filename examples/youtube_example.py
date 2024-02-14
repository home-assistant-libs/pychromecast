"""
Example on how to use the YouTube Controller

"""

# pylint: disable=invalid-name

import argparse
import sys
from time import sleep

import pychromecast
from pychromecast.controllers.youtube import YouTubeController

from .common import add_log_arguments, configure_logging


# Enable deprecation warnings etc.
if not sys.warnoptions:
    import warnings

    warnings.simplefilter("default")

# Change to the name of your Chromecast
CAST_NAME = "Living Room TV"

# Change to the video id of the YouTube video
# video id is the last part of the url http://youtube.com/watch?v=video_id
VIDEO_ID = "dQw4w9WgXcQ"


parser = argparse.ArgumentParser(
    description="Example on how to use the Youtube Controller."
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
    "--videoid", help='Youtube video ID (default: "%(default)s")', default=VIDEO_ID
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

yt = YouTubeController()
cast.register_handler(yt)
yt.play_video(VIDEO_ID)

# If debugging, sleep after running so we can see any error messages.
if args.show_debug:
    sleep(10)

# Shut down discovery
browser.stop_discovery()
