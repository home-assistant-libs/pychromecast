"""
Example on how to use the Media Controller.

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
parser.add_argument(
    "--show-status-only", help="Show status, then exit", action="store_true"
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

print()
print(cast.cast_info)
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
    t = 5.0
    while cast.status.app_id is not None and t > 0:  # type: ignore[union-attr]
        time.sleep(0.1)
        t = t - 0.1

print(f'Playing media "{args.url}"')
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
browser.stop_discovery()
