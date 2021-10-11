"""
Example on how to use the YouTube Controller

"""
# pylint: disable=invalid-name

import argparse
import logging
import sys
import zeroconf

import pychromecast
from pychromecast.controllers.youtube import YouTubeController


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
parser.add_argument("--show-debug", help="Enable debug log", action="store_true")
parser.add_argument(
    "--show-zeroconf-debug", help="Enable zeroconf debug log", action="store_true"
)
parser.add_argument(
    "--videoid", help='Youtube video ID (default: "%(default)s")', default=VIDEO_ID
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

yt = YouTubeController()
cast.register_handler(yt)
yt.play_video(VIDEO_ID)

# Shut down discovery
browser.stop_discovery()
