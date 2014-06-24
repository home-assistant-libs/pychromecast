"""
Example code to show how you can start a YouTube movie
whenever the idle screen is shown.
"""
import time

import pychromecast

if __name__ == "__main__":
    cast = pychromecast.get_chromecast(strict=False)

    while True:
        cast.refresh()

        if cast.app_id == pychromecast.APP_ID['HOME']:
            print "Hey, we are on the home screen :( Starting YouTube.."
            pychromecast.play_youtube_video("kxopViU98Xo", ip=cast.host)

        time.sleep(10)
