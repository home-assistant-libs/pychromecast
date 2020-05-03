"""
Example on how to use the Media Controller

"""

import argparse
import logging
import sys
import time

import pychromecast

# Change to the friendly name of your Chromecast
CAST_NAME = "Living Room"

# Change to an audio or video url
MEDIA_URL = "https://a.files.bbci.co.uk/media/live/manifesto/audio/simulcast/dash/nonuk/dash_low/llnws/bbc_radio_fourfm.mpd"

parser = argparse.ArgumentParser(
    description="Example on how to use the Media Controller to play an URL."
)
parser.add_argument("--show-debug", help="Enable debug log", action="store_true")
parser.add_argument(
    "--cast", help='Name of cast device (default: "%(default)s")', default=CAST_NAME
)
parser.add_argument(
    "--url", help='Media url (default: "%(default)s")', default=MEDIA_URL
)
args = parser.parse_args()

if args.show_debug:
    logging.basicConfig(level=logging.DEBUG)

chromecasts = pychromecast.get_listed_chromecasts(friendly_names=[args.cast])
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
cast.media_controller.play_media(args.url, "audio/mp3")

# Wait for player_state PLAYING
player_state = None
t = 30
while player_state != "PLAYING" and t > 0:
    try:
        if player_state != cast.media_controller.status.player_state:
            player_state = cast.media_controller.status.player_state
            print("Player state:", player_state)

        time.sleep(0.1)
        t = t - 0.1
    except KeyboardInterrupt:
        break
