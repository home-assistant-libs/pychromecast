"""
Test Spotify Controller.
NOTE: You need to install the spotipy and spotify-token dependencies.

This can be done by running the following:
pip install git+https://github.com/plamere/spotipy.git

You must manually enter the token that you can retrieve into your 
cookie in the spotify web app (wp_access_token)
"""
import pychromecast
from pychromecast.controllers.spotify import SpotifyController
import spotipy

chromecasts = pychromecast.get_chromecasts()
cast = chromecasts[1]

device_id = None

if cast:
    print("I test with device : {}".format(cast.name))

    print("Open Spotify web app (https://open.spotify.com) in your browser and "
        "search the wp_access_token in cookies")

    access_token = input("access token : ").strip()

    client = spotipy.Spotify(auth=access_token)
    print("Client Spotify connected : {}".format(client.me().get('id')))

    print("Test launch spotify app in chromecast {}".format(cast.name))
    sp = SpotifyController(access_token)
    cast.register_handler(sp)
    sp.launch_app()

    devices_available = client.devices()

    for device in devices_available['devices']:
        if device['name'] == cast.name and device['type'] == 'CastVideo':
            device_id = device['id']
            break

    client.start_playback(device_id=device_id, uris=["spotify:track:3Zwu2K0Qa5sT6teCCHPShP"])
