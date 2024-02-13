"""
Example that shows how to connect to all chromecasts.
"""
# pylint: disable=invalid-name

import argparse
import sys

import pychromecast

from .common import add_log_arguments, configure_logging

# Enable deprecation warnings etc.
if not sys.warnoptions:
    import warnings

    warnings.simplefilter("default")

parser = argparse.ArgumentParser(
    description="Example on how to connect to all chromecasts."
)
parser.add_argument(
    "--known-host",
    help="Add known host (IP), can be used multiple times",
    action="append",
)
add_log_arguments(parser)
args = parser.parse_args()

configure_logging(args)

casts, browser = pychromecast.get_chromecasts(known_hosts=args.known_host)
# Shut down discovery as we don't care about updates
browser.stop_discovery()
if len(casts) == 0:
    print("No Devices Found")
    sys.exit(1)

print("Found cast devices:")
for cast in casts:
    print(
        f'  "{cast.name}" on mDNS/host service {cast.cast_info.services} with UUID:{cast.uuid}'
    )
