"""
Example that shows how to list chromecasts.
"""
import argparse
import logging

import pychromecast

parser = argparse.ArgumentParser(description="Example on how to list chromecasts.")
parser.add_argument("--show-debug", help="Enable debug log", action="store_true")
args = parser.parse_args()

if args.show_debug:
    logging.basicConfig(level=logging.DEBUG)

casts, browser = pychromecast.get_chromecasts()
# Shut down discovery as we don't care about updates
pychromecast.discovery.stop_discovery(browser)
if len(casts) == 0:
    print("No Devices Found")
    exit()

print("Found cast devices:")
for cast in casts:
    print(
        '  "{}" on mDNS service {} with UUID:{}'.format(
            cast.name, cast._services, cast.uuid
        )
    )
