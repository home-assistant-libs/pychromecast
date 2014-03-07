"""
Examples of how PyChromecast can be used.
"""

import time

import pychromecast as pc

cast = pc.PyChromecast()
print cast.device
print "Current app:", cast.app

# Make sure an app is running that supports RAMP protocol
if not cast.app or pc.PROTOCOL_RAMP not in cast.app.service_protocols:
    pc.play_youtube_video("kxopViU98Xo", cast.host)

ramp = cast.get_protocol(pc.PROTOCOL_RAMP)

while not ramp:
    time.sleep(5)
    cast.refresh()
    ramp = cast.get_protocol(pc.PROTOCOL_RAMP)

# Give ramp some time to init
time.sleep(.5)

print "Ramp:", ramp

print "Toggling play status"
ramp.playpause()

# Give some time to get new status
time.sleep(1)

print "Ramp:", ramp

exit()
