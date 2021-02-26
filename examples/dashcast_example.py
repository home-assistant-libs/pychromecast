"""
Example that shows how the DashCast controller can be used.
"""
# pylint: disable=invalid-name

import argparse
import logging
import sys
import time

import zeroconf

import pychromecast
import pychromecast.controllers.dashcast as dashcast

# Change to the friendly name of your Chromecast
CAST_NAME = "Living Room"

parser = argparse.ArgumentParser(
    description="Example that shows how the DashCast controller can be used."
)
parser.add_argument("--show-debug", help="Enable debug log", action="store_true")
parser.add_argument(
    "--show-zeroconf-debug", help="Enable zeroconf debug log", action="store_true"
)
parser.add_argument(
    "--cast", help='Name of cast device (default: "%(default)s")', default=CAST_NAME
)
args = parser.parse_args()

if args.show_debug:
    logging.basicConfig(level=logging.DEBUG)
if args.show_zeroconf_debug:
    print("Zeroconf version: " + zeroconf.__version__)
    logging.getLogger("zeroconf").setLevel(logging.DEBUG)

chromecasts, browser = pychromecast.get_listed_chromecasts(friendly_names=[args.cast])
if not chromecasts:
    print('No chromecast with name "{}" discovered'.format(args.cast))
    sys.exit(1)

cast = chromecasts[0]
# Start socket client's worker thread and wait for initial status update
cast.wait()

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
    t = 5
    while cast.status.app_id is not None and t > 0:
        time.sleep(0.1)
        t = t - 0.1

time.sleep(1)

# Test that the callback chain works. This should send a message to
# load the first url, but immediately after send a message load the
# second url.
warning_message = "If you see this on your TV then something is broken"
d.load_url(
    "https://home-assistant.io/? " + warning_message,
    callback_function=lambda result: d.load_url("https://home-assistant.io/"),
)

# If debugging, sleep after running so we can see any error messages.
if args.show_debug:
    time.sleep(10)

# Shut down discovery
browser.stop_discovery()
