"""
Controller to interface with the Yle Areena app namespace.
"""

from .media import BaseMediaPlayer, STREAM_TYPE_BUFFERED, TYPE_LOAD, MESSAGE_TYPE
from ..config import APP_YLEAREENA
from ..error import PyChromecastError
from ..response_handler import WaitResponse


class YleAreenaController(BaseMediaPlayer):
    """Controller to interact with Yle Areena app namespace."""

    def __init__(self):
        super().__init__(supporting_app_id=APP_YLEAREENA)

    def play_areena_media(  # pylint: disable=too-many-locals
        self,
        kaltura_id,
        audio_language="",
        text_language="off",
        current_time=0,
        autoplay=True,
        stream_type=STREAM_TYPE_BUFFERED,
        callback_function=None,
    ):
        """
        Play media with the entry id "kaltura_id".
        This value can be found by loading a page on Areena, e.g. https://areena.yle.fi/1-50097921
        And finding the kaltura player which has an id of yle-kaltura-player3430579305188-29-0_whwjqpry
        In this case the kaltura id is 0_whwjqpry
        """
        msg = {
            "media": {
                "streamType": stream_type,
                "customData": {
                    "mediaInfo": {"entryId": kaltura_id},
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

        self.send_message(msg, inc_session_id=True, callback_function=callback_function)

    # pylint: disable-next=arguments-differ
    def quick_play(self, media_id=None, audio_lang="", text_lang="off", **kwargs):
        """Quick Play"""
        response_handler = WaitResponse(10)
        self.play_areena_media(
            media_id,
            audio_language=audio_lang,
            text_language=text_lang,
            **kwargs,
            callback_function=response_handler.callback
        )
        request_completed = response_handler.wait_response()

        if not request_completed or not response_handler.msg_sent:
            self.logger.warning("Quick Play failed for %s:(%s)", media_id, kwargs)
            raise PyChromecastError()  # pylint: disable=broad-exception-raised
