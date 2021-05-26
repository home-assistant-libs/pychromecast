"""
Controller to interface with BBC iPlayer.
https://www.bbc.co.uk/iplayer
"""
import logging

from . import BaseController
from ..config import APP_BBCIPLAYER
from .media import STREAM_TYPE_BUFFERED, STREAM_TYPE_LIVE

APP_NAMESPACE = "urn:x-cast:com.google.cast.media"

class BbcIplayerController(BaseController):
    """Controller to interact with BBC iPlayer namespace."""

    def __init__(self):
        super().__init__(APP_NAMESPACE, APP_BBCIPLAYER)

        self.logger = logging.getLogger(__name__)

    def play_media(self, media_id, is_live=False, **kwargs):
        """
        Play BBC iPlayer media
        """
        streamType = STREAM_TYPE_LIVE if is_live else STREAM_TYPE_BUFFERED 
        metadata = kwargs.get("metadata", { "metadataType": 0, "title": "" })
        subtitle = metadata.pop("subtitle", "")

        msg = {
                "media": {
                    "contentId": media_id,
                    "customData": {
                        "secondary_title": subtitle
                    },
                    "metadata": metadata,
                    "streamType": streamType
                },
                "type": "LOAD"
        }
        self.send_message(msg, inc_session_id=False)

    def quick_play(self, media_id=None, is_live=False, **kwargs):
        """Quick Play"""
        self.play_media(media_id, is_live=is_live, **kwargs)
