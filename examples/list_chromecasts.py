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

casts = pychromecast.get_chromecasts()
if len(casts) == 0:
    print("No Devices Found")
    exit()

print("Found cast devices:")
for cast in casts:
    print(
        '  "{}" on {}:{} with UUID:{}'.format(
            cast.name, cast.host, cast.port, cast.uuid
        )
    )
