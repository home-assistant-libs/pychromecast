"""
Example on how to use the YouTube Controller

"""

import pychromecast
from pychromecast.controllers.youtube import YouTubeController


# Change to the name of your Chromecast
CAST_NAME = "Living Room TV"

# Change to the video id of the YouTube video
# video id is the last part of the url http://youtube.com/watch?v=video_id
VIDEO_ID = ""


chromecasts = pychromecast.get_chromecasts()
cast = next(cc for cc in chromecasts if cc.device.friendly_name == CAST_NAME)
cast.start()
cast.wait()
yt = YouTubeController()
cast.register_handler(yt)
yt.play_video(VIDEO_ID)
