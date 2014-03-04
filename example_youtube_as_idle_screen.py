"""
Example code to show how you can start a YouTube movie
whenever the idle screen is shown.
"""
import sys
import time

import pychromecast

if len(sys.argv) != 2:
    print "Call script with Chromecast-IP as argument."
    print "Example: python {} 192.168.1.9".format(__file__)
    exit()

host = sys.argv[1]

cast = pychromecast.PyChromecast(host)

while True:
    cast.refresh()

    if cast.app_id == pychromecast.APP_ID['HOME']:
        print "Hey, we are on the home screen :( Starting YouTube.."
        pychromecast.play_youtube_video(host, "kxopViU98Xo")

    time.sleep(10)
