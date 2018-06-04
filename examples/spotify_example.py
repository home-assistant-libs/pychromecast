"""
Example on how to use the Spotify Controller.
NOTE: You need to install the spotipy and spotify-token dependencies.

This can be done by running the following:
pip install git+https://github.com/plamere/spotipy.git

You must declare your application to Spotify
https://developer.spotify.com/dashboard/
When you have create your app, you must specify the "Redirect URIs"
in "EDIT SETTINGS".
Ex value : http://localhost
At the first launch you will be redirected to your browser to 
allow the application.
"""
import pychromecast
from pychromecast.controllers.spotify import SpotifyController
import spotipy.util as util
import spotipy

chromecasts = pychromecast.get_chromecasts()
cast = chromecasts[0]

CAST_NAME = "My Chromecast"
device_id = None

# Spotify developer informations
USERNAME="spotify_user" # edit
CLIENT_ID= "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" # edit
CLIENT_SECRET="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" # edit
REDIRECT_URI = 'http://localhost' # edit if you have change
# Scope for full access, adapt to needs
SCOPE = 'playlist-read-private playlist-read-collaborative playlist-modify-public '\
        'playlist-modify-private streaming ugc-image-upload user-follow-modify '\
        'user-follow-read user-library-read user-library-modify user-read-private '\
        'user-read-birthdate user-read-email user-top-read user-read-playback-state '\
        'user-modify-playback-state user-read-currently-playing user-read-recently-played'
# Request access token to spotify
access_token = util.prompt_for_user_token(USERNAME, scope=SCOPE, client_id=CLIENT_ID, 
                    client_secret=CLIENT_SECRET, redirect_uri=REDIRECT_URI)

if cast.name == CAST_NAME:

    client = spotipy.Spotify(auth=access_token)

    sp = SpotifyController(access_token)
    cast.register_handler(sp)
    sp.launch_app()

    devices_available = client.devices()

    for device in devices_available['devices']:
        if device['name'] == CAST_NAME and device['type'] == 'CastVideo':
            device_id = device['id']
            break

    client.start_playback(device_id=device_id, uris=["spotify:track:3Zwu2K0Qa5sT6teCCHPShP"])