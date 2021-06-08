"""
Controller to interface with BBC Sounds.
"""
# Media ID can be found in the URL
# e.g. https://www.bbc.co.uk/sounds/live:bbc_radio_one

import logging

from . import BaseController
from ..config import APP_BBCSOUNDS
from .media import STREAM_TYPE_BUFFERED, STREAM_TYPE_LIVE

APP_NAMESPACE = "urn:x-cast:com.google.cast.media"


class BbcSoundsController(BaseController):
    """Controller to interact with BBC Sounds namespace."""

    def __init__(self):
        super().__init__(APP_NAMESPACE, APP_BBCSOUNDS)

        self.logger = logging.getLogger(__name__)

    def play_media(self, media_id, is_live=False, **kwargs):
        """Play BBC Sounds media"""
        stream_type = STREAM_TYPE_LIVE if is_live else STREAM_TYPE_BUFFERED
        metadata_default = {"metadataType": 0, "title": ""}

        msg = {
            "media": {
                "contentId": media_id,
                "metadata": kwargs.get("metadata", metadata_default),
                "streamType": stream_type,
            },
            "type": "LOAD",
        }

        self.send_message(msg, inc_session_id=False)

    def quick_play(self, media_id=None, is_live=False, **kwargs):
        """Quick Play"""
        self.play_media(media_id, is_live=is_live, **kwargs)
