"""
Example that shows how to connect to all chromecasts.
"""
# pylint: disable=invalid-name

import argparse
import logging
import sys

import zeroconf

import pychromecast

parser = argparse.ArgumentParser(
    description="Example on how to connect to all chromecasts."
)
parser.add_argument("--show-debug", help="Enable debug log", action="store_true")
parser.add_argument(
    "--show-zeroconf-debug", help="Enable zeroconf debug log", action="store_true"
)
args = parser.parse_args()

if args.show_debug:
    logging.basicConfig(level=logging.DEBUG)
if args.show_zeroconf_debug:
    print("Zeroconf version: " + zeroconf.__version__)
    logging.getLogger("zeroconf").setLevel(logging.DEBUG)

casts, browser = pychromecast.get_chromecasts()
# Shut down discovery as we don't care about updates
browser.stop_discovery()
if len(casts) == 0:
    print("No Devices Found")
    sys.exit(1)

print("Found cast devices:")
for cast in casts:
    print(
        '  "{}" on mDNS service {} with UUID:{}'.format(
            cast.name, cast._services, cast.uuid  # pylint: disable=protected-access
        )
    )
