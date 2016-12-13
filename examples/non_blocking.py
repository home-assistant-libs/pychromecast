"""
Example that shows how the new Python 2 socket client can be used.

All functions (except get_chromecast()) are non-blocking and
return immediately without waiting for the result. You can use
that functionality to include pychromecast into your main loop.
"""

from __future__ import print_function
import time
import select
import sys
import logging

import pychromecast

"""
Put this code into your startup/init code.
This one is the only blocking part.
"""
def initialize_chromecast():
    print("Initialize Chromecast (blocking)...takes some time")
    cast = pychromecast.get_chromecast(friendly_name="Wohnzimmer",
                                       blocking=False)
    return cast

"""
Check for cast.socket_client.get_socket() and
handle it with cast.socket_client.run_once()
"""
def your_main_loop(cast):
    t = 1
    while True:
        polltime = 0.1
        can_read, _, _ = select.select([cast.socket_client.get_socket()], [], [], polltime)
        if can_read:
            #received something on the socket, handle it with run_once()
            cast.socket_client.run_once()
        do_actions(cast, t)
        time.sleep(1)
        t += 1
        if(t > 50):
           break

"""
Your code which is called by main loop
"""
def do_actions(cast, t):
    if t == 5:
        print()
        print("=> Sending non-blocking play_media command")
        cast.play_media(
            ("http://commondatastorage.googleapis.com/gtv-videos-bucket/"
             "sample/BigBuckBunny.mp4"), "video/mp4")
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

if '--show-debug' in sys.argv:
    logging.basicConfig(level=logging.DEBUG)
else:
    logging.basicConfig(level=logging.INFO)

cast = initialize_chromecast()
your_main_loop(cast)

