"""
Controller to interface with BBC iPlayer.
"""
# Note: Media ID is NOT the 8 digit alpha-numeric in the URL
# it can be found by right clicking the playing video on the web interface
# e.g. https://www.bbc.co.uk/iplayer/episode/b09w7fd9/bitz-bob-series-1-1-castle-makeover shows:
# "2908kbps | dash (mf_cloudfront_dash_https)
#  b09w70r2 | 960x540"

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
        """Play BBC iPlayer media"""
        stream_type = STREAM_TYPE_LIVE if is_live else STREAM_TYPE_BUFFERED
        metadata = kwargs.get("metadata", {"metadataType": 0, "title": ""})
        subtitle = metadata.pop("subtitle", "")

        msg = {
            "media": {
                "contentId": media_id,
                "customData": {"secondary_title": subtitle},
                "metadata": metadata,
                "streamType": stream_type,
            },
            "type": "LOAD",
        }
        self.send_message(msg, inc_session_id=False)

    def quick_play(self, media_id=None, is_live=False, **kwargs):
        """Quick Play"""
        self.play_media(media_id, is_live=is_live, **kwargs)
