"""
Example on how to use the Media Controller to play an URL.

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
MEDIA_URL = "https://www.bensound.com/bensound-music/bensound-jazzyfrenchy.mp3"

parser = argparse.ArgumentParser(
    description="Example on how to use the Media Controller to play an URL."
)
add_log_arguments(parser)
parser.add_argument(
    "--cast", help='Name of cast device (default: "%(default)s")', default=CAST_NAME
)
parser.add_argument(
    "--known-host",
    help="Add known host (IP), can be used multiple times",
    action="append",
)
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
print(f'Found chromecast with name "{args.cast}", attempting to play "{args.url}"')
cast.media_controller.play_media(args.url, "audio/mp3")

# Wait for player_state PLAYING
player_state = None
t = 30.0
has_played = False
while True:
    try:
        if player_state != cast.media_controller.status.player_state:
            player_state = cast.media_controller.status.player_state
            print("Player state:", player_state)
        if player_state == "PLAYING":
            has_played = True
        if (
            cast.connection_client.connected
            and has_played
            and player_state != "PLAYING"
        ):
            has_played = False
            cast.media_controller.play_media(args.url, "audio/mp3")

        time.sleep(0.1)
        t = t - 0.1
    except KeyboardInterrupt:
        break

# Shut down discovery
browser.stop_discovery()
