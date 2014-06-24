"""
Examples of how PyChromecast can be used.
"""

import time

import pychromecast as pc

cast = pc.get_single_chromecast(friendly_name='Living Room')
print cast.device
print "Current app:", cast.app

# Make sure an app is running that supports RAMP protocol
if not cast.app or pc.PROTOCOL_RAMP not in cast.app.service_protocols:
    pc.play_youtube_video("kxopViU98Xo", cast.host)
    cast.refresh()

ramp = cast.get_protocol(pc.PROTOCOL_RAMP)

# It can take some time to setup websocket connection
# if we just switched to a new channel
while not ramp:
    time.sleep(1)
    ramp = cast.get_protocol(pc.PROTOCOL_RAMP)

# Give ramp some time to init
time.sleep(10)

print "Ramp:", ramp

print "Toggling play status"
ramp.playpause()

# Give some time to get new status
time.sleep(1)

print "Ramp:", ramp
