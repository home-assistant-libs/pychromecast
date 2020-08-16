"""
Example on how to use the Media Controller

"""

import argparse
import logging
import sys
import time

import pychromecast
import zeroconf

# Change to the friendly name of your Chromecast
CAST_NAME = "Living Room speaker"

# Change to an audio or video url
MEDIA_URLS = [
    "https://a.files.bbci.co.uk/media/live/manifesto/audio/simulcast/dash/nonuk/dash_low/llnws/bbc_radio_fourfm.mpd",
    "https://www.bensound.com/bensound-music/bensound-jazzyfrenchy.mp3",
    "https://incompetech.com/music/royalty-free/mp3-royaltyfree/The%20Sky%20of%20our%20Ancestors.mp3"
]


parser = argparse.ArgumentParser(
    description="Example on how to use the Media Controller with a queue."
)
parser.add_argument("--show-debug", help="Enable debug log", action="store_true")
parser.add_argument("--show-zeroconf-debug", help="Enable zeroconf debug log", action="store_true")
parser.add_argument(
    "--cast", help='Name of cast device (default: "%(default)s")', default=CAST_NAME
)
args = parser.parse_args()

if args.show_debug:
    logging.basicConfig(level=logging.DEBUG)
if args.show_zeroconf_debug:
    print("Zeroconf version: " + zeroconf.__version__)
    logging.getLogger("zeroconf").setLevel(logging.DEBUG)

chromecasts, browser = pychromecast.get_listed_chromecasts(friendly_names=[args.cast])
if not chromecasts:
    print('No chromecast with name "{}" discovered'.format(args.cast))
    sys.exit(1)

cast = chromecasts[0]
# Start socket client's worker thread and wait for initial status update
cast.wait()
print('Found chromecast with name "{}"'.format(args.cast))

cast.media_controller.play_media(MEDIA_URLS[0], "audio/mp3")

# Wait for Chromecast to start playing
while (cast.media_controller.status.player_state != "PLAYING"):
    time.sleep(0.1)

# Queue next items
for URL in MEDIA_URLS[1:]:
    cast.media_controller.queue_media(URL, "audio/mp3")

for URL in MEDIA_URLS[1:]:
    time.sleep(5)
    cast.media_controller.queue_next()

# Shut down discovery
pychromecast.discovery.stop_discovery(browser)
