"""
Example on how to use the BBC iPlayer Controller

"""
# pylint: disable=invalid-name

import logging
from time import sleep
import sys

import pychromecast
from pychromecast.controllers.bbciplayer import BbcIplayerController

# Change to the name of your Chromecast
CAST_NAME = "Lounge Video"

# Note: Media ID is NOT the 8 digit alpha-numeric in the URL
# it can be found by right clicking the playing video on the web interface
# e.g. https://www.bbc.co.uk/iplayer/episode/b09w7fd9/bitz-bob-series-1-1-castle-makeover shows: 
# "2908kbps | dash (mf_cloudfront_dash_https)
#  b09w70r2 | 960x540"
MEDIA_ID = 'b09w70r2'
metadata = {
	"metadata": {
		"metadatatype": 0,
		"title": "Bitz & Bob",
        "subtitle": "Castle Makeover",
		"images": [{
			"url": "https://ichef.bbci.co.uk/images/ic/1280x720/p07j4m3r.jpg"
		}]
	}
}

logging.basicConfig(level=logging.DEBUG)

chromecasts, browser = pychromecast.get_listed_chromecasts(friendly_names=[CAST_NAME])
if not chromecasts:
    print('No chromecast with name "{}" discovered'.format(CAST_NAME))
    sys.exit(1)

cast = chromecasts[0]
# Start socket client's worker thread and wait for initial status update
cast.wait()

bbciplayer = BbcIplayerController()
cast.register_handler(bbciplayer)
bbciplayer.launch()
bbciplayer.quick_play(MEDIA_ID, False, **metadata)
cast.wait()

sleep(10)