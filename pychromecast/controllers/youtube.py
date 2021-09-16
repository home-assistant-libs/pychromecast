"""
Controller to interface with the YouTube-app.
Use the media controller to play, pause etc.
"""
import logging
import threading
from casttube import YouTubeSession

from . import BaseController
from ..const import MESSAGE_TYPE
from ..error import UnsupportedNamespace
from ..config import APP_YOUTUBE

YOUTUBE_NAMESPACE = "urn:x-cast:com.google.youtube.mdx"
TYPE_GET_SCREEN_ID = "getMdxSessionStatus"
TYPE_STATUS = "mdxSessionStatus"
ATTR_SCREEN_ID = "screenId"
_LOGGER = logging.getLogger(__name__)


class YouTubeController(BaseController):
    """Controller to interact with Youtube."""

    def __init__(self):
        super().__init__(YOUTUBE_NAMESPACE, APP_YOUTUBE)
        self.status_update_event = threading.Event()
        self._screen_id = None
        self._session = None

    def start_session_if_none(self):
        """
        Starts a session it is not yet initialized.
        """
        if not (self._screen_id and self._session):
            self.update_screen_id()
            self._session = YouTubeSession(screen_id=self._screen_id)

    def play_video(self, video_id, playlist_id=None):
        """
        Play video(video_id) now. This ignores the current play queue order.
        :param video_id: YouTube video id(http://youtube.com/watch?v=video_id)
        :param playlist_id: youtube.com/watch?v=video_id&list=playlist_id
        """
        self.start_session_if_none()
        self._session.play_video(video_id, playlist_id)

    def add_to_queue(self, video_id):
        """
        Add video(video_id) to the end of the play queue.
        :param video_id: YouTube video id(http://youtube.com/watch?v=video_id)
        """
        self.start_session_if_none()
        self._session.add_to_queue(video_id)

    def play_next(self, video_id):
        """
        Play video(video_id) after the currently playing video.
        :param video_id: YouTube video id(http://youtube.com/watch?v=video_id)
        """
        self.start_session_if_none()
        self._session.play_next(video_id)

    def remove_video(self, video_id):
        """
        Remove video(videoId) from the queue.
        :param video_id: YouTube video id(http://youtube.com/watch?v=video_id)
        """
        self.start_session_if_none()
        self._session.remove_video(video_id)

    def clear_playlist(self):
        """
        Clear the entire video queue
        """
        self.start_session_if_none()
        self._session.clear_playlist()

    def update_screen_id(self):
        """
        Sends a getMdxSessionStatus to get the screenId and waits for response.
        This function is blocking
        If connected we should always get a response
        (send message will launch app if it is not running).
        """
        self.status_update_event.clear()
        # This gets the screenId but always throws. Couldn't find a better way.
        try:
            self.send_message({MESSAGE_TYPE: TYPE_GET_SCREEN_ID})
        except UnsupportedNamespace:
            pass
        status = self.status_update_event.wait(10)
        if not status:
            _LOGGER.warning("Failed to update screen_id")
        self.status_update_event.clear()

    def receive_message(self, _message, data: dict):
        """Called when a message is received."""
        if data[MESSAGE_TYPE] == TYPE_STATUS:
            self._process_status(data.get("data"))
            return True

        return False

    def _process_status(self, status):
        """Process latest status update."""
        self._screen_id = status.get(ATTR_SCREEN_ID)
        self.status_update_event.set()

    def quick_play(self, media_id=None, playlist_id=None, enqueue=False, **kwargs):
        """Quick Play"""
        if enqueue:
            self.add_to_queue(media_id, **kwargs)
        else:
            self.play_video(media_id, playlist_id=playlist_id, **kwargs)
