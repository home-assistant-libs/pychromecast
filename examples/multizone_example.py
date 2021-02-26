"""
Example on how to use the Multizone (Audio Group) Controller

"""
# pylint: disable=invalid-name

import argparse
import logging
import sys
import time

import zeroconf

import pychromecast
from pychromecast.controllers.multizone import (
    MultizoneController,
    MultiZoneControllerListener,
)
from pychromecast.socket_client import ConnectionStatusListener

# Change to the name of your Chromecast
CAST_NAME = "Whole house"

parser = argparse.ArgumentParser(
    description="Example on how to use the Multizone Controller to track groupp members."
)
parser.add_argument("--show-debug", help="Enable debug log", action="store_true")
parser.add_argument(
    "--show-zeroconf-debug", help="Enable zeroconf debug log", action="store_true"
)
parser.add_argument(
    "--cast", help='Name of speaker group (default: "%(default)s")', default=CAST_NAME
)
args = parser.parse_args()

if args.show_debug:
    logging.basicConfig(level=logging.DEBUG)
if args.show_zeroconf_debug:
    print("Zeroconf version: " + zeroconf.__version__)
    logging.getLogger("zeroconf").setLevel(logging.DEBUG)


class MyConnectionStatusListener(ConnectionStatusListener):
    """ConnectionStatusListener"""

    def __init__(self, _mz):
        self._mz = _mz

    def new_connection_status(self, status):
        if status.status == "CONNECTED":
            self._mz.update_members()


class MyMultiZoneControllerListener(MultiZoneControllerListener):
    """MultiZoneControllerListener"""

    def multizone_member_added(self, group_uuid):
        print("New member: {}".format(group_uuid))

    def multizone_member_removed(self, group_uuid):
        print("Removed member: {}".format(group_uuid))

    def multizone_status_received(self):
        print("Members: {}".format(mz.members))


chromecasts, browser = pychromecast.get_listed_chromecasts(friendly_names=[args.cast])
if not chromecasts:
    print('No chromecast with name "{}" discovered'.format(args.cast))
    sys.exit(1)

cast = chromecasts[0]
# Add listeners
mz = MultizoneController(cast.uuid)
mz.register_listener(MyMultiZoneControllerListener())
cast.register_handler(mz)
cast.register_connection_listener(MyConnectionStatusListener(mz))

# Start socket client's worker thread and wait for initial status update
cast.wait()

while True:
    try:
        time.sleep(1)
    except KeyboardInterrupt:
        break

# Shut down discovery
browser.stop_discovery()
