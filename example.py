"""
Examples of how PyChromecast can be used.
"""

import time

import pychromecast


host = "192.168.1.9"

cast = pychromecast.PyChromecast(host)
print cast.device
print "Current app:", cast.app

# Make sure an app is running that supports RAMP protocol
if not cast.app or pychromecast.PROTOCOL_RAMP not in cast.app.service_protocols:
    pychromecast.play_youtube_video(host, "kxopViU98Xo")


ramp = None
while not ramp:
    time.sleep(1)

    ramp = cast.get_protocol(pychromecast.PROTOCOL_RAMP)

print "Ramp:", ramp
ramp.playpause()

time.sleep(1)  # Give the twisted engine some time to send command

print "Ramp:", ramp

exit()

