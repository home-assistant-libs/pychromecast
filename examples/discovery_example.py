"""
Example that shows how to receive updates on discovered chromecasts.
"""
import argparse
import logging
import time

import pychromecast

parser = argparse.ArgumentParser(description="Example on how to receive updates on discovered chromecasts.")
parser.add_argument("--show-debug", help="Enable debug log", action="store_true")
args = parser.parse_args()

if args.show_debug:
    logging.basicConfig(level=logging.DEBUG)

def list_devices():
     print("Currently known cast devices:")
     for name, service in listener.services.items():
         print("  {} {}".format(name, service))

def add_callback(name):
    print("Found cast device {}".format(name))
    list_devices()

def remove_callback(name, service):
    print("Lost cast device {} {}".format(name, service))
    list_devices()

listener = pychromecast.CastListener(add_callback, remove_callback)
browser = pychromecast.discovery.start_discovery(listener)

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass

pychromecast.stop_discovery(browser)
