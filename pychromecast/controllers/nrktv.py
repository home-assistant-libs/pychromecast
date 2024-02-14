"""
Controller to interface with NRK TV.
"""

# Note: Media ID for live programs can be found in the URL
# e.g. for https://tv.nrk.no/direkte/nrk1, the media ID is nrk1
# Media ID for non-live programs can be found by clicking the share button
# e.g. https://tv.nrk.no/serie/uti-vaar-hage/sesong/2/episode/2 shows:
# "https://tv.nrk.no/se?v=OUHA43000207", the media ID is OUHA43000207

from .media import BaseMediaPlayer
from ..config import APP_NRKTV

APP_NAMESPACE = "urn:x-cast:com.google.cast.media"


class NrkTvController(BaseMediaPlayer):
    """Controller to interact with NRK TV."""

    def __init__(self) -> None:
        super().__init__(supporting_app_id=APP_NRKTV)
