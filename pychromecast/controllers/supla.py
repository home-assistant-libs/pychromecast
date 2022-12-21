"""
Controller to interface with Supla.
"""
import logging
import threading

from . import BaseController
from ..config import APP_SUPLA
from ..error import PyChromecastError

APP_NAMESPACE = "urn:x-cast:fi.ruutu.chromecast"


# pylint: disable=too-many-instance-attributes
class SuplaController(BaseController):
    """Controller to interact with Supla namespace."""

    def __init__(self):
        super().__init__(APP_NAMESPACE, APP_SUPLA)

        self.logger = logging.getLogger(__name__)

    def play_media(self, media_id, is_live=False, callback_function=None):
        """
        Play Supla media
        """
        msg = {
            "type": "load",
            "mediaId": media_id,
            "currentTime": 0,
            "isLive": is_live,
            "isAtLiveMoment": False,
            "bookToken": "",
            "sample": True,
            "fw_site": "Supla",
            "Sanoma_adkv": "",
            "prerollAdsPlayed": True,
            "supla": True,
            "nextInSequenceList": 0,
            "playbackRate": 1,
            "env": "prod",
        }

        self.send_message(
            msg,
            inc_session_id=False,
            callback_function=callback_function,
            no_add_request_id=True,
        )

    def quick_play(self, media_id=None, is_live=False, **kwargs):
        """Quick Play"""
        play_media_done_event = threading.Event()

        def play_media_done(_):
            play_media_done_event.set()

        self.play_media(
            media_id, is_live=is_live, callback_function=play_media_done, **kwargs
        )
        play_media_done_event.wait(10)
        if not play_media_done_event.is_set():
            raise PyChromecastError()
