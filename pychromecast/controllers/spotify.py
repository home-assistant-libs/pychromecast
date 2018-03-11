from pychromecast.controllers import BaseController
import logging

logging.basicConfig(level=logging.DEBUG)


class SpotifyController(BaseController):
    def __init__(self):
        super(SpotifyController, self).__init__(
            "urn:x-cast:com.spotify.chromecast.secure.v1", "CC32E753")

    def receive_message(self, message, data):
        print("Cast message: {}".format(data))

        return True  # indicate you handled this message

    def start_playback(self, credentials):

        def callback():
            self.send_message({"type":"setCredentials","credentials":credentials},inc_session_id=True)

        self.launch(callback_function=callback)
