"""
Example that shows how to list all available chromecasts.
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
    description="Example that shows how to list all available chromecasts."
)
parser.add_argument(
    "--known-host",
    help="Add known host (IP), can be used multiple times",
    action="append",
)
add_log_arguments(parser)
parser.add_argument(
    "--verbose", help="Full display of discovered devices", action="store_true"
)
args = parser.parse_args()

configure_logging(args)

devices, browser = pychromecast.discovery.discover_chromecasts(
    known_hosts=args.known_host
)
# Shut down discovery
browser.stop_discovery()

print(f"Discovered {len(devices)} device(s):")
for device in devices:
    print(
        f"  '{device.friendly_name}' ({device.model_name}) @ {device.host}:{device.port} uuid: {device.uuid}"
    )
    if args.verbose:
        print(f"  service: {device}")
