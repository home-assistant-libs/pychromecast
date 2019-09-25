"""
Example on how to use the YouTube Controller

"""

import os
import pychromecast
import time
from pychromecast.controllers.youtube_tv import YouTubeTVController
from requests_oauthlib import OAuth2Session

# From https://requests-oauthlib.readthedocs.io/en/latest/examples/google.html
client_id = '.apps.googleusercontent.com'
client_secret = ''
# It doesn't matter what you put here as long as you have authorized it on your
# Google Developer console, since you will just be pasting this URL in below.
# The http/https matters here.
redirect_uri = 'http://raspberrypi.com:5000/callback'

# This allows us to use a plain HTTP callback (uncomment if redirect_uri is http)
# os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = "1"

authorization_base_url = "https://accounts.google.com/o/oauth2/v2/auth"
token_url = "https://www.googleapis.com/oauth2/v4/token"
scope = [
    "https://www.googleapis.com/auth/youtube"
]

google_requests_handler = OAuth2Session(client_id, scope=scope, redirect_uri=redirect_uri)

authorization_url, state = google_requests_handler.authorization_url(authorization_base_url,
    # offline for refresh token
    # force to always make user click authorize
    access_type="offline", prompt="select_account")

print('Please go here and authorize,', authorization_url)

redirect_response = input('Paste the full redirect URL here:')

google_requests_handler.fetch_token(token_url, client_secret=client_secret,
    authorization_response=redirect_response)

# Change to the name of your Chromecast
CAST_NAME = "Living Room TV"

# Change to the video id of the YouTube video
# video id is the last part of the url https://tv.youtube.com/watch/video_id
VIDEO_ID = ""

chromecasts = pychromecast.get_chromecasts()
cast = next(cc for cc in chromecasts if cc.device.friendly_name == CAST_NAME)
cast.wait()
yt = YouTubeTVController(google_requests_handler)
cast.register_handler(yt)
yt.play_video(VIDEO_ID)