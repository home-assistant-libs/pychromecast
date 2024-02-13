"""
Controller to interface with Supla.
"""

import logging
from typing import Any

from . import CallbackType, QuickPlayController
from ..config import APP_SUPLA
from ..response_handler import WaitResponse

APP_NAMESPACE = "urn:x-cast:fi.ruutu.chromecast"


# pylint: disable=too-many-instance-attributes
class SuplaController(QuickPlayController):
    """Controller to interact with Supla namespace."""

    def __init__(self) -> None:
        super().__init__(APP_NAMESPACE, APP_SUPLA)

        self.logger = logging.getLogger(__name__)

    def play_media(
        self,
        media_id: str,
        *,
        is_live: bool = False,
        callback_function: CallbackType | None = None,
    ) -> None:
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

    def quick_play(
        self, *, media_id: str, timeout: float, is_live: bool = False, **kwargs: Any
    ) -> None:
        """Quick Play"""
        response_handler = WaitResponse(timeout, f"supla quick play {media_id}")
        self.play_media(
            media_id,
            is_live=is_live,
            **kwargs,
            callback_function=response_handler.callback,
        )
        response_handler.wait_response()
