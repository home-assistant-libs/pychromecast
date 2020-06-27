"""
Example that shows how to receive updates on discovered chromecasts.
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

def list_devices():
    print("Currently known cast devices:")
    for uuid, service in listener.services.items():
        print("  {} {}".format(uuid, service))

def add_callback(uuid, name):
    print("Found mDNS service for cast device {}".format(uuid))
    list_devices()

def remove_callback(uuid, name, service):
    print("Lost mDNS service for cast device {} {}".format(uuid, service))
    list_devices()

def update_callback(uuid, name):
    print("Updated mDNS service for cast device {}".format(uuid))
    list_devices()

listener = pychromecast.CastListener(add_callback, remove_callback, update_callback)
zconf = zeroconf.Zeroconf()
browser = pychromecast.discovery.start_discovery(listener, zconf)

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass

pychromecast.stop_discovery(browser)
