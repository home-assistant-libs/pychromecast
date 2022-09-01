"""
Example that shows how to list chromecasts matching on name or uuid.
"""
# pylint: disable=invalid-name

import argparse
import logging
import sys
from uuid import UUID

import zeroconf

import pychromecast

parser = argparse.ArgumentParser(
    description="Example that shows how to list chromecasts matching on name or uuid."
)
parser.add_argument("--cast", help='Name of wanted cast device")', default=None)
parser.add_argument("--uuid", help="UUID of wanted cast device", default=None)
parser.add_argument(
    "--known-host",
    help="Add known host (IP), can be used multiple times",
    action="append",
)
parser.add_argument("--show-debug", help="Enable debug log", action="store_true")
parser.add_argument(
    "--show-zeroconf-debug", help="Enable zeroconf debug log", action="store_true"
)
parser.add_argument(
    "--verbose", help="Full display of discovered devices", action="store_true"
)
args = parser.parse_args()

if args.show_debug:
    logging.basicConfig(level=logging.DEBUG)
if args.show_zeroconf_debug:
    print("Zeroconf version: " + zeroconf.__version__)
    logging.getLogger("zeroconf").setLevel(logging.DEBUG)

if args.cast is None and args.uuid is None:
    print("Need to supply `cast` or `uuid`")
    sys.exit(1)

friendly_names = []
if args.cast:
    friendly_names.append(args.cast)

uuids = []
if args.uuid:
    uuids.append(UUID(args.uuid))

devices, browser = pychromecast.discovery.discover_listed_chromecasts(
    friendly_names=friendly_names, uuids=uuids, known_hosts=args.known_host
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
