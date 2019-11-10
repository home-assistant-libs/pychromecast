"""
Controller to interface with the Yle Areena app namespace.
"""

from ..config import APP_YLEAREENA
from .media import MediaController, STREAM_TYPE_BUFFERED, TYPE_LOAD, MESSAGE_TYPE


class YleAreenaController(MediaController):
    """ Controller to interact with Yle Areena app namespace. """

    # pylint: disable=useless-super-delegation
    def __init__(self):
        super(YleAreenaController, self).__init__()

        self.app_id = APP_YLEAREENA

    # pylint: disable=too-many-arguments
    def play_areena_media(
        self,
        entry_id="",
        audio_language="",
        text_language="off",
        current_time=0,
        autoplay=True,
        stream_type=STREAM_TYPE_BUFFERED,
    ):
        """
        Play media with the entry id "entry_id".
        This value can be found by loading a page on Areena, e.g. https://areena.yle.fi/1-50097921
        And finding the kaltura player which has an id of yle-kaltura-player3430579305188-29-0_whwjqpry
        In this case the entry id is 0_whwjqpry
        """

        # pylint: disable=too-many-locals
        def app_launched_callback():
            """Plays media after chromecast has switched to requested app."""

            self._send_start_play_media(
                entry_id,
                audio_language,
                text_language,
                current_time,
                autoplay,
                stream_type,
            )

        receiver_ctrl = self._socket_client.receiver_controller
        receiver_ctrl.launch_app(self.app_id, callback_function=app_launched_callback)

    def _send_start_play_areena_media(
        self,
        entry_id,
        audio_language="",
        text_language="off",
        current_time=0,
        autoplay=True,
        stream_type=STREAM_TYPE_BUFFERED,
    ):
        # pylint: disable=too-many-locals
        msg = {
            "media": {
                "streamType": stream_type,
                "customData": {
                    "mediaInfo": {"entryId": entry_id},
                    "audioLanguage": audio_language,
                    "textLanguage": text_language,
                },
            },
            MESSAGE_TYPE: TYPE_LOAD,
            "currentTime": current_time,
            "autoplay": autoplay,
            "customData": {},
            "textTrackStyle": {
                "foregroundColor": "#FFFFFFFF",
                "backgroundColor": "#000000FF",
                "fontScale": 1,
                "fontFamily": "sans-serif",
            },
        }

        self.send_message(msg, inc_session_id=True)
