"""
Examples of how PyChromecast can be used.
"""

import time

import pychromecast


cast = pychromecast.PyChromecast()
print cast.device
print "Current app:", cast.app

# Make sure an app is running that supports RAMP protocol
if not cast.app or pychromecast.PROTOCOL_RAMP not in cast.app.service_protocols:
    pychromecast.play_youtube_video(cast.host, "kxopViU98Xo")


ramp = cast.get_protocol(pychromecast.PROTOCOL_RAMP)

while not ramp:
    time.sleep(5)
    cast.refresh()
    ramp = cast.get_protocol(pychromecast.PROTOCOL_RAMP)

# Wait till client comes alive.
while not ramp.is_active:
	time.sleep(1)

print "Ramp:", ramp

ramp.playpause()

time.sleep(1)  # Give the twisted engine some time to send command

print "Ramp:", ramp

exit()
