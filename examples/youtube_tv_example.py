"""
Example on how to use the YouTube Controller

"""

import pychromecast
import time
from pychromecast.controllers.youtube_tv import YouTubeTVController

# Add the required Authentication Cookies. These can be found by browsing to YouTube TV,
# logging in, opening the element inspector and browsing to 
# Application > Storage > Cookies > https://tv.youtube.com
# and filling in the matching cookie values below.
cookies = {
    "APISID": "", 
    "HSID": "", 
    "SAPISID": "", 
    "SID": "", 
    "SSID": "",
}

# Change to the name of your Chromecast
CAST_NAME = "Living Room TV"

# Change to the video id of the YouTube video
# video id is the last part of the url https://tv.youtube.com/watch/video_id
VIDEO_ID = ""

chromecasts = pychromecast.get_chromecasts()
cast = next(cc for cc in chromecasts if cc.device.friendly_name == CAST_NAME)
cast.wait()
yt = YouTubeTVController(cookies)
cast.register_handler(yt)
yt.play_video(VIDEO_ID)
