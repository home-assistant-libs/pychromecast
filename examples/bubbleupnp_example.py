"""
Example on how to use the BubbleUPNP Controller

"""
import logging
import sys
from time import sleep

import pychromecast
from pychromecast.controllers.bubbleupnp import BubbleUPNPController


# Change to the name of your Chromecast
CAST_NAME = "Kitchen speaker"

URL = "https://c3.toivon.net/toivon/toivon_3?mp=/stream"

logging.basicConfig(level=logging.DEBUG)

# pylint: disable=unbalanced-tuple-unpacking
chromecasts, browser = pychromecast.get_listed_chromecasts(friendly_names=[CAST_NAME])
if not chromecasts:
    print('No chromecast with name "{}" discovered'.format(CAST_NAME))
    sys.exit(1)

cast = list(chromecasts)[0]
# Start socket client's worker thread and wait for initial status update
cast.wait()

bubbleupnp = BubbleUPNPController()
cast.register_handler(bubbleupnp)
bubbleupnp.launch()
bubbleupnp.play_media(URL, "audio/mp3", stream_type="LIVE")
cast.wait()

sleep(10)
