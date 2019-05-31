"""
Controller to interface with the Plex-app.
"""
from . import BaseController

MESSAGE_TYPE = 'type'
SEEK_KEY = "currentTime"

TYPE_PLAY = "PLAY"
TYPE_PAUSE = "PAUSE"
TYPE_STOP = "STOP"
TYPE_SEEK = "SEEK"


class PlexController(BaseController):
    """ Controller to interact with Plex namespace. """

    def __init__(self):
        super(PlexController, self).__init__(
            "urn:x-cast:plex", "9AC194DC")

    def stop(self):
        """ Send stop command. """
        self.send_message({MESSAGE_TYPE: TYPE_STOP})

    def pause(self):
        """ Send pause command. """
        self.send_message({MESSAGE_TYPE: TYPE_PAUSE})

    def play(self):
        """ Send play command. """
        self.send_message({MESSAGE_TYPE: TYPE_PLAY})

    def seek(self, time):
        """ Send seek command.

        :param time (int): Time in seconds to seek to
        """
        self.send_message({MESSAGE_TYPE: TYPE_SEEK,
                           SEEK_KEY: time})
