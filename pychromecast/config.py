"""
Data and methods to retrieve app specific configuration
"""
import json

import requests


APP_ID = {
    "HOME": "00000000-0000-0000-0000-000000000000",
    "YOUTUBE": "YouTube",
    "NETFLIX": "Netflix",
    "TICTACTOE": "TicTacToe",
    "GOOGLE_MUSIC": "GoogleMusic",
    "PLAY_MOVIES": "PlayMovies",
    "HULU_PLUS": "Hulu_Plus",
    "HBO": "HBO_App",
    "PANDORA": "Pandora_App",
    "REDBULLTV": "edaded98-5119-4c8a-afc1-de722da03562",
    "VIKI": "1812335e-441c-4e1e-a61a-312ca1ead90e",
    "PLEX_QA": "06ee44ee-e7e3-4249-83b6-f5d0b6f07f34",
    "PLEX": "06ee44ee-e7e3-4249-83b6-f5d0b6f07f34_1",
    "VEVO": "2be788b9-b7e0-4743-9069-ea876d97ac20",
    "AVIA": "aa35235e-a960-4402-a87e-807ae8b2ac79",
    "REVISION3": "Revision3_App",
    "SONGZA": "Songza_App",
    "REALPLAYER_CLOUD": "a7f3283b-8034-4506-83e8-4e79ab1ad794_2",
    "BEYONDPOD": "18a8aeaa-8e3d-4c24-b05d-da68394a3476_1",
    "WASHINGTON_POST": "Post_TV_App",
    "DEFAULT_MEDIA_RECEIVER": "CC1AD845",
}


def get_possible_app_ids():
    """ Returns all possible app ids. """

    try:
        req = requests.get(
            "https://clients3.google.com/cast/chromecast/device/baseconfig")
        data = json.loads(req.text[4:])

        return [app['app_id'] for app in data['applications']] + \
            data["enabled_app_ids"]

    except ValueError:
        # If json fails to parse
        return []


def get_app_config(app_id):
    """ Get specific configuration for 'app_id'. """
    try:
        req = requests.get(
            ("https://clients3.google.com/"
             "cast/chromecast/device/app?a={}").format(app_id))

        return json.loads(req.text[4:]) if req.status_code == 200 else {}

    except ValueError:
        # If json fails to parse
        return {}
