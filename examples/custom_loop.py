"""
Example that shows how the socket client can be used without its own worker
thread by not calling Chromecast.start() or Chromecast.wait(), but instead calling
Chromecast.connect().

You can use that functionality to include pychromecast into your main loop.
"""
# pylint: disable=invalid-name

import argparse
import logging
import select
import time

import zeroconf

import pychromecast

CAST_NAME = "Living Room"


def your_main_loop():
    """
    Main loop example.
    Check for cast.socket_client.get_socket() and
    handle it with cast.socket_client.run_once()
    """

    t = 1
    cast = None

    def callback(chromecast):
        if chromecast.name == args.cast:
            print("=> Discovered cast...")
            chromecast.connect()
            nonlocal cast
            cast = chromecast

    browser = pychromecast.get_chromecasts(blocking=False, callback=callback)

    while True:
        if cast:
            polltime = 0.1
            can_read, _, _ = select.select(
                [cast.socket_client.get_socket()], [], [], polltime
            )
            if can_read:
                # received something on the socket, handle it with run_once()
                cast.socket_client.run_once()
            do_actions(cast, t)
            t += 1
            if t > 50:
                break
        else:
            print("=> Waiting for discovery of cast '{}'...".format(args.cast))
        time.sleep(1)

    print("All done, shutting down discovery")
    browser.stop_discovery()


def do_actions(cast, t):
    """Your code which is called by main loop."""
    if t == 5:
        print()
        print("=> Sending non-blocking play_media command")
        cast.play_media(
            (
                "http://commondatastorage.googleapis.com/gtv-videos-bucket/"
                "sample/BigBuckBunny.mp4"
            ),
            "video/mp4",
        )
    elif t == 30:
        print()
        print("=> Sending non-blocking pause command")
        cast.media_controller.pause()
    elif t == 35:
        print()
        print("=> Sending non-blocking play command")
        cast.media_controller.play()
    elif t == 40:
        print()
        print("=> Sending non-blocking stop command")
        cast.media_controller.stop()
    elif t == 45:
        print()
        print("=> Sending non-blocking quit_app command")
        cast.quit_app()
    elif t % 4 == 0:
        print()
        print("Media status", cast.media_controller.status)


parser = argparse.ArgumentParser(description="Example without socket_client thread")
parser.add_argument("--show-debug", help="Enable debug log", action="store_true")
parser.add_argument(
    "--show-zeroconf-debug", help="Enable zeroconf debug log", action="store_true"
)
parser.add_argument(
    "--cast", help='Name of cast device (default: "%(default)s")', default=CAST_NAME
)
args = parser.parse_args()

if args.show_debug:
    logging.basicConfig(level=logging.DEBUG)
else:
    logging.basicConfig(level=logging.INFO)
if args.show_zeroconf_debug:
    print("Zeroconf version: " + zeroconf.__version__)
    logging.getLogger("zeroconf").setLevel(logging.DEBUG)

your_main_loop()
