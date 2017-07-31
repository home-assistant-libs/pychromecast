"""
Example that shows how the chromecast-dashboard controller can be used.

Functions called in this example are blocking which means that
the function doesn't return as long as no result was received.
"""

from __future__ import print_function
import time
import sys
import logging

import pychromecast
import pychromecast.controllers.chromecastDashboard as dashboard

if '--show-debug' in sys.argv:
    logging.basicConfig(level=logging.DEBUG)

casts = pychromecast.get_chromecasts()
if len(casts) == 0:
    print("No Devices Found")
    exit()
cast = next(cc for cc in casts if cc.device.friendly_name == "Bedroom Display")
#cast = casts[0]

d = dashboard.ChromecastDashboardController()
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

d.load_url('http://hass.io')

