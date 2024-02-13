"""
Example on how to use queuing with Media Controller

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
MEDIA_URLS = [
    "https://www.bensound.com/bensound-music/bensound-jazzyfrenchy.mp3",
    "https://audio.guim.co.uk/2020/08/14-65292-200817TIFXR.mp3",
]


parser = argparse.ArgumentParser(
    description="Example on how to use the Media Controller with a queue."
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
print(f'Found chromecast with name "{args.cast}"')

cast.media_controller.play_media(MEDIA_URLS[0], "audio/mp3")

# Wait for Chromecast to start playing
while cast.media_controller.status.player_state != "PLAYING":
    time.sleep(0.1)

# Queue next items
for URL in MEDIA_URLS[1:]:
    print("Enqueuing...")
    cast.media_controller.play_media(URL, "audio/mp3", enqueue=True)


for URL in MEDIA_URLS[1:]:
    time.sleep(5)
    print("Skipping...")
    cast.media_controller.queue_next()

# Shut down discovery
browser.stop_discovery()
