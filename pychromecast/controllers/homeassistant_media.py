"""
Simple Controller to use the Home Assistant Media Player Cast App as a media controller.
"""

from ..config import APP_HOMEASSISTANT_MEDIA
from .media import MediaController


class HomeAssistantMediaController(MediaController):
    """Controller to interact with HomeAssistantMedia app namespace."""

    def __init__(self):
        super().__init__()
        self.app_id = APP_HOMEASSISTANT_MEDIA
        self.supporting_app_id = APP_HOMEASSISTANT_MEDIA

    def quick_play(self, media_id=None, media_type="video/mp4", **kwargs):
        """Quick Play"""
        self.play_media(media_id, media_type, **kwargs)
