"""
Simple Controller to use BubbleUPNP as a media controller.
"""

from .media import BaseMediaPlayer
from ..config import APP_BUBBLEUPNP


class BubbleUPNPController(BaseMediaPlayer):
    """Controller to interact with BubbleUPNP app namespace."""

    def __init__(self) -> None:
        super().__init__(supporting_app_id=APP_BUBBLEUPNP)
