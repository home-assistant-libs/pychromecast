"""
Example that shows how to list available chromecasts.
"""
import argparse
import logging
import time

import pychromecast
import zeroconf

parser = argparse.ArgumentParser(description="Example on how to receive updates on discovered chromecasts.")
parser.add_argument("--show-debug", help="Enable debug log", action="store_true")
args = parser.parse_args()

if args.show_debug:
    logging.basicConfig(level=logging.DEBUG)

devices, browser = pychromecast.discovery.discover_chromecasts()
# Shut down discovery
pychromecast.stop_discovery(browser)

print(f"Discovered {len(devices)} device(s):")
for device in devices:
    print(f"  {device}")
    
