"""
Controller to interface with the YouTube-TV-app.
Use the media controller to play, pause etc.
"""
import threading
from casttube import YouTubeTVSession

from .youtube import YouTubeController
from ..config import APP_YOUTUBE_TV

YOUTUBE_NAMESPACE = "urn:x-cast:com.google.youtube.mdx"


class YouTubeTVController(YouTubeController):
    """ Controller to interact with Youtube TV."""

    def __init__(self, cookies=None):
        super(YouTubeTVController, self).__init__(
            YOUTUBE_NAMESPACE, APP_YOUTUBE_TV)
        self.status_update_event = threading.Event()
        self._screen_id = None
        self._session = None
        self._cookies = cookies

    def start_session_if_none(self):
        """
        Starts a session it is not yet initialized.
        """
        if not (self._screen_id and self._session):
            self.update_screen_id()
            self._session = YouTubeTVSession(
                screen_id=self._screen_id,
                cookies=self._cookies
            )
