"""
Example on how to use the Multizone (Audio Group) Controller

"""
# pylint: disable=invalid-name

import argparse
import sys
import time

import pychromecast
from pychromecast.controllers.multizone import (
    MultizoneController,
    MultiZoneControllerListener,
)
from pychromecast.socket_client import ConnectionStatus, ConnectionStatusListener

from .common import add_log_arguments, configure_logging

# Enable deprecation warnings etc.
if not sys.warnoptions:
    import warnings

    warnings.simplefilter("default")

# Change to the name of your Chromecast
CAST_NAME = "Whole house"

parser = argparse.ArgumentParser(
    description="Example on how to use the Multizone Controller to track groupp members."
)
parser.add_argument(
    "--cast", help='Name of speaker group (default: "%(default)s")', default=CAST_NAME
)
parser.add_argument(
    "--known-host",
    help="Add known host (IP), can be used multiple times",
    action="append",
)
add_log_arguments(parser)
args = parser.parse_args()

configure_logging(args)


class MyConnectionStatusListener(ConnectionStatusListener):
    """ConnectionStatusListener"""

    def __init__(self, _mz: MultizoneController):
        self._mz = _mz

    def new_connection_status(self, status: ConnectionStatus) -> None:
        if status.status == "CONNECTED":
            self._mz.update_members()


class MyMultiZoneControllerListener(MultiZoneControllerListener):
    """MultiZoneControllerListener"""

    def multizone_member_added(self, group_uuid: str) -> None:
        print(f"New member: {group_uuid}")

    def multizone_member_removed(self, group_uuid: str) -> None:
        print(f"Removed member: {group_uuid}")

    def multizone_status_received(self) -> None:
        print(f"Members: {mz.members}")


chromecasts, browser = pychromecast.get_listed_chromecasts(
    friendly_names=[args.cast], known_hosts=args.known_host
)
if not chromecasts:
    print(f'No chromecast with name "{args.cast}" discovered')
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
