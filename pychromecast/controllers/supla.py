"""
Controller to interface with Supla.
"""
import logging

from . import BaseController
from ..config import APP_SUPLA

APP_NAMESPACE = "urn:x-cast:fi.ruutu.chromecast"


# pylint: disable=too-many-instance-attributes
class SuplaController(BaseController):
    """ Controller to interact with Supla namespace. """

    # pylint: disable=useless-super-delegation
    # The pylint rule useless-super-delegation doesn't realize
    # we are setting default values here.
    def __init__(self):
        super(SuplaController, self).__init__(APP_NAMESPACE, APP_SUPLA)

        self.logger = logging.getLogger(__name__)

    # pylint: enable=useless-super-delegation

    def play_media(self, media_id, is_live=False):
        msg = {
            "type": "load",
            "mediaId": media_id,
            "currentTime": 0,
            "isLive": is_live,
            "isAtLiveMoment": False,
            "bookToken": "",
            "sample": True,
            "fw_site": "Supla",
            "Sanoma_adkv": "",
            "prerollAdsPlayed": True,
            "supla": True,
            "nextInSequenceList": 0,
            "playbackRate": 1,
            "env": "prod"
        }
        self.send_message(msg, inc_session_id=True)

    def quick_play(self, media_id=None, is_live=False, media_type=False, match=None):
        if media_type == 'program':
            import requests
            from bs4 import BeautifulSoup
            result = requests.get("https://www.supla.fi/ohjelmat/{}".format(media_id))
            soup = BeautifulSoup(result.content)
            query = 'a[href*="/audio"]'
            if match:
                query += '[title*="{}"]'.format(match)
            try:
                media_id = soup.select(query)[0]["href"].split("/")[-1]
            except (IndexError, KeyError):
                media_id = None

        if not media_id:
            raise AttributeError('Media not found')
        self.play_media(media_id, is_live=is_live)
