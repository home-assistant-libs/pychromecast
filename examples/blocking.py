"""
Example that shows how the new Python 2 socket client can be used.

Functions called in this example are blocking which means that
the function doesn't return as long as no result was received.
"""

from __future__ import print_function
import time
import sys
import logging

import pychromecast
import pychromecast.controllers.youtube as youtube

if '--show-debug' in sys.argv:
    logging.basicConfig(level=logging.DEBUG)

casts = pychromecast.get_chromecasts()
if len(casts) == 0:
    print("No Devices Found")
    exit()
cast = casts[0]

yt = youtube.YouTubeController()
cast.register_handler(yt)

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

print("Playing media")
cast.play_media(
    ("http://commondatastorage.googleapis.com/gtv-videos-bucket/"
     "sample/BigBuckBunny.mp4"), "video/mp4")

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
        elif t == 27:
            print("Switching to YouTube")
            yt.play_video("L0MK7qz13bU")
        elif t == 38:
            cast.media_controller.pause()
        elif t == 45:
            cast.quit_app()
            break

        time.sleep(1)
    except KeyboardInterrupt:
        break
