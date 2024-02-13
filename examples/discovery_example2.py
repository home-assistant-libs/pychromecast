"""
Example that shows how to list all available chromecasts.
"""
# pylint: disable=invalid-name

import argparse
import logging
import sys

import zeroconf

import pychromecast

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
parser.add_argument("--show-debug", help="Enable debug log", action="store_true")
parser.add_argument(
    "--show-discovery-debug", help="Enable discovery debug log", action="store_true"
)
parser.add_argument(
    "--show-zeroconf-debug", help="Enable zeroconf debug log", action="store_true"
)
parser.add_argument(
    "--verbose", help="Full display of discovered devices", action="store_true"
)
args = parser.parse_args()

if args.show_debug:
    fmt = "%(asctime)s %(levelname)s (%(threadName)s) [%(name)s] %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    logging.basicConfig(format=fmt, datefmt=datefmt, level=logging.DEBUG)
    logging.getLogger("pychromecast.dial").setLevel(logging.INFO)
    logging.getLogger("pychromecast.discovery").setLevel(logging.INFO)
if args.show_discovery_debug:
    logging.getLogger("pychromecast.dial").setLevel(logging.DEBUG)
    logging.getLogger("pychromecast.discovery").setLevel(logging.DEBUG)
if args.show_zeroconf_debug:
    print("Zeroconf version: " + zeroconf.__version__)
    logging.getLogger("zeroconf").setLevel(logging.DEBUG)

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
