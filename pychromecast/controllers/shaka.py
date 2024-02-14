"""
Simple Controller to use Shaka as a media controller.
"""

from ..config import APP_SHAKA
from .media import BaseMediaPlayer


class ShakaController(BaseMediaPlayer):
    """Controller to interact with Shaka app namespace."""

    def __init__(self) -> None:
        super().__init__(supporting_app_id=APP_SHAKA)
