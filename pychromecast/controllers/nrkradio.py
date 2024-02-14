"""
Controller to interface with NRK Radio.
"""

# Note: Media ID can be found in the URL, e.g:
# For the live channel https://radio.nrk.no/direkte/p1, the media ID is p1
# For the podcast https://radio.nrk.no/podkast/tazte_priv/l_8457deb0-4f2c-4ef3-97de-b04f2c6ef314,
# the Media ID is l_8457deb0-4f2c-4ef3-97de-b04f2c6ef314
# For the on-demand program https://radio.nrk.no/serie/radiodokumentaren/sesong/201011/MDUP01004510,
# the media id is MDUP01004510

from .media import BaseMediaPlayer
from ..config import APP_NRKRADIO

APP_NAMESPACE = "urn:x-cast:com.google.cast.media"


class NrkRadioController(BaseMediaPlayer):
    """Controller to interact with NRK Radio."""

    def __init__(self) -> None:
        super().__init__(supporting_app_id=APP_NRKRADIO)
