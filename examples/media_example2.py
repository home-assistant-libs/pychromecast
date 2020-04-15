"""
Example that shows how the socket client can be used.

Functions called in this example are blocking which means that
the function doesn't return as long as no result was received.
"""
import argparse
import logging
import sys
import time

import pychromecast

# Change to the name of your Chromecast
CAST_NAME = "Disco room"

# Change to an audio or video url
MEDIA_URL = "http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"

parser = argparse.ArgumentParser(
    description="Example on how to use the Spotify Controller.")
parser.add_argument('--show-debug', help='Enable debug log',
                    action='store_true')
parser.add_argument('--cast',
                    help='Name of cast device (default: "%(default)s")',
                    default=CAST_NAME)
parser.add_argument('--url', help='Media url (default: "%(default)s")',
                    default=MEDIA_URL)
args = parser.parse_args()

if args.show_debug:
    logging.basicConfig(level=logging.DEBUG)

chromecasts = pychromecast.get_listed_chromecasts(friendly_names=[args.cast])
cast = None
for _cast in chromecasts:
    if _cast.name == args.cast:
        cast = _cast
        break

if not cast:
    print('No chromecast with name "{}" discovered'.format(args.cast))
    sys.exit(1)

cast.wait()

print()
print(cast.device)
time.sleep(1)
print()
print(cast.status)
print()
print(cast.media_controller.status)
print()

if '--show-status-only' in sys.argv:
    sys.exit()

if not cast.is_idle:
    print("Killing current running app")
    cast.quit_app()
    time.sleep(5)

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
