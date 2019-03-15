"""
Example on how to use the Spotify Controller.
NOTE: You need to install the spotipy and spotify-token dependencies.

This can be done by running the following:
pip install spotify-token
pip install git+https://github.com/plamere/spotipy.git
"""
import logging
import sys

import pychromecast
from pychromecast.controllers.spotify import SpotifyController
import spotify_token as st
import spotipy

CAST_NAME = "My Chromecast"

debug = '--show-debug' in sys.argv
if debug:
    logging.basicConfig(level=logging.DEBUG)

chromecasts = pychromecast.get_chromecasts()
cast = None
for _cast in chromecasts:
    if _cast.name == CAST_NAME:
        cast = _cast
        break

if cast:
    cast.wait()
    device_id = None

    data = st.start_session("SPOTIFY_USERNAME", "SPOTIFY_PASSWORD")
    access_token = data[0]

    client = spotipy.Spotify(auth=access_token)

    sp = SpotifyController(access_token)
    cast.register_handler(sp)
    sp.launch_app()

    devices_available = client.devices()

    for device in devices_available['devices']:
        if device['name'] == CAST_NAME:
            device_id = device['id']
            break

    client.start_playback(device_id=device_id, uris=["spotify:track:3Zwu2K0Qa5sT6teCCHPShP"])