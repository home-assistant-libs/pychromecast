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

if '--show-debug' in sys.argv:
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

d.load_url('https://home-assistant.io')
