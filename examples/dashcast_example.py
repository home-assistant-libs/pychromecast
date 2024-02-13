"""
Example that shows how the DashCast controller can be used.
"""
# pylint: disable=invalid-name

import argparse
import sys
import time
import threading

import pychromecast
from pychromecast.controllers import dashcast

from .common import add_log_arguments, configure_logging

# Enable deprecation warnings etc.
if not sys.warnoptions:
    import warnings

    warnings.simplefilter("default")

# Change to the friendly name of your Chromecast
CAST_NAME = "Living Room"

parser = argparse.ArgumentParser(
    description="Example that shows how the DashCast controller can be used."
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

cast = chromecasts[0]
# Start socket client's worker thread and wait for initial status update
cast.wait()

d = dashcast.DashCastController()
cast.register_handler(d)

print()
print(cast.cast_info)
time.sleep(1)
print()
print(cast.status)
print()
print(cast.media_controller.status)
print()

if not cast.is_idle:
    print("Killing current running app")
    cast.quit_app()
    t = 5.0
    while cast.status.app_id is not None and t > 0:  # type: ignore[union-attr]
        time.sleep(0.1)
        t = t - 0.1

time.sleep(1)

requests_handled = threading.Event()


def _first_request_handled(msg_sent: bool, _response: dict | None) -> None:
    """Request to load first URL handled, load the second URL."""
    if not msg_sent:
        print("Failed to load first URL")

    print("Loaded 1st URL, loading 2nd URL")
    d.load_url("https://home-assistant.io/", callback_function=_second_request_handled)


def _second_request_handled(msg_sent: bool, _response: dict | None) -> None:
    """Request to load second URL handled."""
    if not msg_sent:
        print("Failed to load second URL")
    print("Loaded 2nd URL")
    requests_handled.set()


# Test that the callback chain works. This should send a message to
# load the first url, but immediately after send a message load the
# second url.
warning_message = "If you see this on your TV then something is broken"

print("Loading 1st URL")
d.load_url(
    "https://home-assistant.io/? " + warning_message,
    callback_function=_second_request_handled,
)

print("Waiting for callbacks")
requests_handled.wait()

# If debugging, sleep after running so we can see any error messages.
if args.show_debug:
    time.sleep(10)

# Shut down discovery
browser.stop_discovery()
