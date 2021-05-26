"""
Example on how to use the BBC iPlayer Controller

"""
# pylint: disable=invalid-name

import logging
from time import sleep
import sys

import pychromecast
from pychromecast.controllers.bbcsounds import BbcSoundsController

# Change to the name of your Chromecast
CAST_NAME = "Lounge Video"

# Media ID can be found in the URL
# e.g. https://www.bbc.co.uk/sounds/live:bbc_radio_one
MEDIA_ID = 'bbc_radio_one'
metadata = {
	"metadata": {
		"metadatatype": 0,
		"title": "Radio 1",
		"images": [{
			"url": "https://sounds.files.bbci.co.uk/2.3.0/networks/bbc_radio_one/background_1280x720.png"
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

bbcsounds = BbcSoundsController()
cast.register_handler(bbcsounds)
bbcsounds.launch()
bbcsounds.quick_play(MEDIA_ID, False, **metadata)
cast.wait()

sleep(10)