"""
Simple Controller to use the Home Assistant Media Player Cast App as a media controller.
"""

from ..config import APP_HOMEASSISTANT_MEDIA
from .media import BaseMediaPlayer


class HomeAssistantMediaController(BaseMediaPlayer):
    """Controller to interact with HomeAssistantMedia app namespace."""

    def __init__(self):
        super().__init__(supporting_app_id=APP_HOMEASSISTANT_MEDIA)
