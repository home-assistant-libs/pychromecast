"""
Simple Controller to use BubbleUPNP as a media controller.
"""

from ..config import APP_BUBBLEUPNP
from .media import BaseMediaPlayer


class BubbleUPNPController(BaseMediaPlayer):
    """Controller to interact with BubbleUPNP app namespace."""

    def __init__(self):
        super().__init__(supporting_app_id=APP_BUBBLEUPNP)
