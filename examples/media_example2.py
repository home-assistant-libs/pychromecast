"""
Example on how to use the Media Controller.

"""
# pylint: disable=invalid-name

import argparse
import logging
import sys
import time

import zeroconf

import pychromecast

# Change to the friendly name of your Chromecast
CAST_NAME = "Living Room"

# Change to an audio or video url
MEDIA_URL = (
    "http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"
)

parser = argparse.ArgumentParser(
    description="Example on how to use the socket client without callbacks."
)
parser.add_argument("--show-debug", help="Enable debug log", action="store_true")
parser.add_argument(
    "--show-zeroconf-debug", help="Enable zeroconf debug log", action="store_true"
)
parser.add_argument(
    "--show-status-only", help="Show status, then exit", action="store_true"
)
parser.add_argument(
    "--cast", help='Name of cast device (default: "%(default)s")', default=CAST_NAME
)
parser.add_argument(
    "--url", help='Media url (default: "%(default)s")', default=MEDIA_URL
)
args = parser.parse_args()

if args.show_debug:
    fmt = "%(asctime)s %(levelname)s (%(threadName)s) [%(name)s] %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    logging.basicConfig(format=fmt, datefmt=datefmt, level=logging.DEBUG)
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

print()
print(cast.device)
time.sleep(1)
print()
print(cast.status)
print()
print(cast.media_controller.status)
print()

if args.show_status_only:
    sys.exit()

if not cast.is_idle:
    print("Killing current running app")
    cast.quit_app()
    t = 5
    while cast.status.app_id is not None and t > 0:
        time.sleep(0.1)
        t = t - 0.1

print('Playing media "{}"'.format(args.url))
cast.play_media(args.url, "video/mp4")

t = 0

while True:
    try:
        t += 1

        if t > 10 and t % 3 == 0:
            print("Media status", cast.media_controller.status)

        if t == 15:
            print("Sending pause command")
            cast.media_controller.pause()
        elif t == 20:
            print("Sending play command")
            cast.media_controller.play()
        elif t == 25:
            print("Sending stop command")
            cast.media_controller.stop()
        elif t == 32:
            cast.quit_app()
            break

        time.sleep(1)
    except KeyboardInterrupt:
        break

# Shut down discovery
pychromecast.discovery.stop_discovery(browser)
