"""
Example that shows how the DashCast controller can be used.

Functions called in this example are blocking which means that
the function doesn't return as long as no result was received.
"""

from __future__ import print_function
import time
import sys
import logging

import pychromecast
import pychromecast.controllers.dashcast as dashcast

debug = '--show-debug' in sys.argv
if debug:
    logging.basicConfig(level=logging.DEBUG)

casts = pychromecast.get_chromecasts()
if len(casts) == 0:
    print("No Devices Found")
    exit()

cast = casts[0]

d = dashcast.DashCastController()
cast.register_handler(d)

print()
print(cast.device)
time.sleep(1)
print()
print(cast.status)
print()
print(cast.media_controller.status)
print()

if not cast.is_idle:
    print("Killing current running app")
    cast.quit_app()
    time.sleep(5)

time.sleep(1)

# Test that the callback chain works. This should send a message to
# load the first url, but immediately after send a message load the
# second url.
warning_message = 'If you see this on your TV then something is broken'
d.load_url('https://home-assistant.io/? ' + warning_message,
           callback_function=lambda result:
           d.load_url('https://home-assistant.io/'))


# If debugging sleep after running so we can see any error messages.
if debug:
    time.sleep(10)

