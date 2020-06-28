"""
Example on how to use the Supla Controller

"""
import logging
import requests
from bs4 import BeautifulSoup

import pychromecast
from time import sleep
from pychromecast.controllers.supla import SuplaController


# Change to the name of your Chromecast
CAST_NAME = "Kitchen Speaker"

# Change to the video id of the YouTube video
# video id is the last part of the url http://youtube.com/watch?v=video_id
PROGRAM = "aamulypsy"


result = requests.get("https://www.supla.fi/ohjelmat/{}".format(PROGRAM))
soup = BeautifulSoup(result.content)
MEDIA_ID = soup.select('a[title*="Koko Shitti"]')[0]["href"].split("/")[-1]
print(MEDIA_ID)


logging.basicConfig(level=logging.DEBUG)

chromecasts, browser = pychromecast.get_listed_chromecasts(friendly_names=[CAST_NAME])
if not chromecasts:
    print('No chromecast with name "{}" discovered'.format(CAST_NAME))
    sys.exit(1)

cast = chromecasts[0]
# Start socket client's worker thread and wait for initial status update
cast.wait()

supla = SuplaController()
cast.register_handler(supla)
supla.launch()
supla.play_media(MEDIA_ID)
cast.wait()

sleep(10)
