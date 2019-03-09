"""
Example showing how to create a simple Chromecast event listener for
device and media status events
"""

import time
import pychromecast


class StatusListener:
    def __init__(self, name, cast):
        self.name = name
        self.cast = cast

    def new_cast_status(self, status):
        print('[',time.ctime(),' - ', self.name,'] status chromecast change:')
        print(status)


class StatusMediaListener:
    def __init__(self, name, cast):
        self.name = name
        self.cast= cast

    def new_media_status(self, status):
        print('[',time.ctime(),' - ', self.name,'] status media change:')
        print(status)


chromecasts = pychromecast.get_chromecasts()
chromecast = next(cc for cc in chromecasts
                  if cc.device.friendly_name == "Living Room Speaker")
chromecast.start()

listenerCast = StatusListener(chromecast.name, chromecast)
chromecast.register_status_listener(listenerCast)

listenerMedia = StatusMediaListener(chromecast.name, chromecast)
chromecast.media_controller.register_status_listener(listenerMedia)

input('Listening for Chromecast events...\n\n')