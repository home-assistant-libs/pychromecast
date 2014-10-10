"""
Example that shows how the new Python 2 socket client can be used.
"""

from __future__ import print_function
import time
import sys
import logging

import pychromecast

if '--show-debug' in sys.argv:
    logging.basicConfig(level=logging.DEBUG)

cast = pychromecast.get_chromecast()
print(cast.device)
time.sleep(1)
print(cast.status)

if not cast.is_idle:
    print("Killing current running app")
    cast.quit_app()
    time.sleep(5)

print("Playing media")
cast.play_media(
    ("http://commondatastorage.googleapis.com/gtv-videos-bucket/"
     "sample/BigBuckBunny.mp4"), pychromecast.STREAM_TYPE_BUFFERED,
     "video/mp4")

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
            cast.quit_app()
            break

        time.sleep(1)
    except KeyboardInterrupt:
        break
