import logging
import sys
import time

import pychromecast
from pychromecast.controllers.spotify import SpotifyController
import spotify_token as st
import spotipy

CAST_NAME = "chromecast_group_name"

debug = '--show-debug' in sys.argv
if debug:
    logging.basicConfig(level=logging.DEBUG)

chromecasts = pychromecast.get_chromecasts()

data = st.start_session("spotify_username", "spotify_password")
access_token = data[0]
expires = data[1] - int(time.time())
client = spotipy.Spotify(auth=access_token)

try:
  for _device in chromecasts:
    sp = None
    _device.wait()
    sp = SpotifyController(access_token, expires)
    _device.register_handler(sp)
    if _device.name == CAST_NAME:
      sp.launch_app()
      spotify_device_name = _device.name

except:
  print('failed to launch app on:', _device.name)
  exit()

for _app in chromecasts:
  if _app.app_id == '531A4F84':
    master_device = _app.name

devices_available = client.devices()
for _spotify_device in devices_available['devices']:
  if _spotify_device['name'] == master_device:
    spotify_device_id = _spotify_device['id']
    client.start_playback(device_id=spotify_device_id, uris=["spotify:track:2PrkQC1PE6Qky5CvE3fsYC"])
