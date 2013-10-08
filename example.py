"""
Examples of how PyChromecast can be used.
"""

import time

from . import pychromecast

host = "192.168.1.120"

# Switch the ChromeCast to the home screen..
pychromecast.quit_app(host)

# .. and give it some time to do so.
time.sleep(4)

# Example using the class
cast = pychromecast.PyChromecast(host)
print cast.device
print "Home screen:", cast.app

cast.app_id = pychromecast.APP_ID_YOUTUBE
print "YouTube status:", cast.app

cast.start_app()

print "YouTube status after opening:", cast.app

# If we are too fast in giving commands the ChromeCast doesn't listen
time.sleep(6)

# Example using the methods
pychromecast.play_youtube_video(host, "kxopViU98Xo")
