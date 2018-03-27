import pychromecast
from pychromecast.controllers.spotify import SpotifyController

chromecasts = pychromecast.get_chromecasts()
cast = chromecasts[0]

CAST_NAME = "My Chromecast"

if cast.name == CAST_NAME:
    sp = SpotifyController(CAST_NAME,"SPOTIFY_USERNAME","SPOTIFY_PASSWORD")
    cast.register_handler(sp)
    sp.launch_app()

    sp.play_song("spotify:track:3Zwu2K0Qa5sT6teCCHPShP")