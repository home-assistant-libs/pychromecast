"""
Example showing how to create a simple Chromecast event listener for
device and media status events
"""

# pylint: disable=invalid-name

import argparse
import sys
import time

import pychromecast
from pychromecast.controllers.media import MediaStatus, MediaStatusListener
from pychromecast.controllers.receiver import CastStatusListener

from .common import add_log_arguments, configure_logging

# Enable deprecation warnings etc.
if not sys.warnoptions:
    import warnings

    warnings.simplefilter("default")

# Change to the friendly name of your Chromecast
CAST_NAME = "Living Room Speaker"


class MyCastStatusListener(CastStatusListener):
    """Cast status listener"""

    def __init__(self, name: str | None, cast: pychromecast.Chromecast) -> None:
        self.name = name
        self.cast = cast

    def new_cast_status(self, status: pychromecast.CastStatus) -> None:
        print("[", time.ctime(), " - ", self.name, "] status chromecast change:")
        print(status)


class MyMediaStatusListener(MediaStatusListener):
    """Status media listener"""

    def __init__(self, name: str | None, cast: pychromecast.Chromecast) -> None:
        self.name = name
        self.cast = cast

    def new_media_status(self, status: MediaStatus) -> None:
        print("[", time.ctime(), " - ", self.name, "] status media change:")
        print(status)

    def load_media_failed(self, queue_item_id: int, error_code: int) -> None:
        print(
            "[",
            time.ctime(),
            " - ",
            self.name,
            "] load media failed for queue item id: ",
            queue_item_id,
            " with code: ",
            error_code,
        )


parser = argparse.ArgumentParser(
    description="Example on how to create a simple Chromecast event listener."
)
parser.add_argument(
    "--cast", help='Name of cast device (default: "%(default)s")', default=CAST_NAME
)
parser.add_argument(
    "--known-host",
    help="Add known host (IP), can be used multiple times",
    action="append",
)
add_log_arguments(parser)
args = parser.parse_args()

configure_logging(args)

chromecasts, browser = pychromecast.get_listed_chromecasts(
    friendly_names=[args.cast], known_hosts=args.known_host
)
if not chromecasts:
    print(f'No chromecast with name "{args.cast}" discovered')
    sys.exit(1)

chromecast = chromecasts[0]
# Start socket client's worker thread and wait for initial status update
chromecast.wait()

listenerCast = MyCastStatusListener(chromecast.name, chromecast)
chromecast.register_status_listener(listenerCast)

listenerMedia = MyMediaStatusListener(chromecast.name, chromecast)
chromecast.media_controller.register_status_listener(listenerMedia)

input("Listening for Chromecast events...\n\n")

# Shut down discovery
browser.stop_discovery()
