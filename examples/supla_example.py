"""
Example on how to use the Supla Controller

"""
# pylint: disable=invalid-name

import logging
from time import sleep
import sys

import requests
from bs4 import BeautifulSoup  # pylint: disable=import-error

import pychromecast
from pychromecast import quick_play


# Change to the name of your Chromecast
CAST_NAME = "Kitchen Speaker"

# Change to the video id of the YouTube video
# video id is the last part of the url http://youtube.com/watch?v=video_id
PROGRAM = "aamulypsy"


result = requests.get(f"https://www.supla.fi/ohjelmat/{PROGRAM}", timeout=10)
soup = BeautifulSoup(result.content)
MEDIA_ID = soup.select('a[title*="Koko Shitti"]')[0]["href"].split("/")[-1]
print(MEDIA_ID)


logging.basicConfig(level=logging.DEBUG)

chromecasts, browser = pychromecast.get_listed_chromecasts(friendly_names=[CAST_NAME])
if not chromecasts:
    print(f'No chromecast with name "{CAST_NAME}" discovered')
    sys.exit(1)

cast = chromecasts[0]
# Start socket client's worker thread and wait for initial status update
cast.wait()

app_name = "supla"
app_data = {
    "media_id": MEDIA_ID,
}
quick_play.quick_play(cast, app_name, app_data)

sleep(10)
