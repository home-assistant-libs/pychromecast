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
        
class ConnectionListener:
    def __init__(self, name, cast):
        self.name = name
        self.cast= cast

    def new_connection_status(self, new_status):
        print('[',time.ctime(),' - ', self.name,'] connection status change:')
        print(new_status)
        # new_status.status = CONNECTING / CONNECTED / DISCONNECTED / FAILED / LOST
        
class LaunchErrorListener:
    def __init__(self, name, cast):
        self.name = name
        self.cast= cast

    def new_launch_error(self, launch_failure):
        print('[',time.ctime(),' - ', self.name,'] status media change:')
        print(launch_failure)
        if launch_failure.reason=="CANCELLED":
            print("Application launched was cancelled !")
            # do some action to recover


chromecasts = pychromecast.get_chromecasts()
chromecast = next(cc for cc in chromecasts
                  if cc.device.friendly_name == "Living Room Speaker")

listenerCast = StatusListener(chromecast.name, chromecast)
chromecast.register_status_listener(listenerCast)

listenerMedia = StatusMediaListener(chromecast.name, chromecast)
chromecast.media_controller.register_status_listener(listenerMedia)

launchErrorCast = LaunchErrorListener(chromecast.name, chromecast)
chromecast.register_launch_error_listener(launchErrorCast)

connectionCast = ConnectionListener(chromecast.name, chromecast)
chromecast.register_connection_listener(connectionCast)

input('Listening for Chromecast events...\n\n')
