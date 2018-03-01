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
Check for cast.socket_client.get_socket() and
handle it with cast.socket_client.run_once()
"""
def your_main_loop():
    t = 1
    cast = None
    def callback(chromecast):
        nonlocal cast
        cast = chromecast
        stop_discovery()

    stop_discovery = pychromecast.get_chromecasts(blocking=False, callback=callback)

    while True:
        if cast:
            polltime = 0.1
            can_read, _, _ = select.select([cast.socket_client.get_socket()], [], [], polltime)
            if can_read:
                #received something on the socket, handle it with run_once()
                cast.socket_client.run_once()
            do_actions(cast, t)
            t += 1
            if(t > 50):
               break
        else:
            print("=> Waiting for cast discovery...")
        time.sleep(1)

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

your_main_loop()

