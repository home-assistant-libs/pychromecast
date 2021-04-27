"""
Simple Controller to use BubbleUPNP as a media controller.
"""

from ..config import APP_BUBBLEUPNP
from .media import MediaController


class BubbleUPNPController(MediaController):
    """Controller to interact with BubbleUPNP app namespace."""

    def __init__(self):
        super().__init__()
        self.app_id = APP_BUBBLEUPNP
        self.supporting_app_id = APP_BUBBLEUPNP

    def quick_play(self, media_id=None, media_type="video/mp4", **kwargs):
        """Quick Play"""
        self.play_media(media_id, media_type, **kwargs)
