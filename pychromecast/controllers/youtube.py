"""
Controller to interface with the YouTube-app.
Use the media controller to play, pause etc.
"""

import logging
import threading
from typing import Any, cast

from casttube import YouTubeSession  # type: ignore[import-untyped]
from casttube.YouTubeSession import HEADERS  # type: ignore[import-untyped]
import requests

from . import QuickPlayController
from ..const import MESSAGE_TYPE
from ..error import RequestTimeout
from ..generated.cast_channel_pb2 import (  # pylint: disable=no-name-in-module
    CastMessage,
)
from ..config import APP_YOUTUBE

YOUTUBE_NAMESPACE = "urn:x-cast:com.google.youtube.mdx"
TYPE_GET_SCREEN_ID = "getMdxSessionStatus"
TYPE_STATUS = "mdxSessionStatus"
ATTR_SCREEN_ID = "screenId"
_LOGGER = logging.getLogger(__name__)


class TimeoutYouTubeSession(YouTubeSession):  # type: ignore[misc]
    """A youtube session with timeout."""

    def __init__(self, screen_id: str, timeout: float) -> None:
        """Initialize."""
        super().__init__(screen_id)
        self.__timeout = timeout

    def _do_post(
        self,
        url: Any,
        data: Any = None,
        params: Any = None,
        headers: Any = None,
        session_request: Any = False,
    ) -> Any:
        """
        Calls requests.post with custom headers,
         increments RID(request id) on every post.
        will raise if response is not 200
        :param url:(str) request url
        :param data: (dict) the POST body
        :param params:(dict) POST url params
        :param headers:(dict) Additional headers for the request
        :param session_request:(bool) True to increment session
         request counter(req_count)
        :return: POST response
        """
        if headers:
            headers = {**HEADERS, **headers}
        else:
            headers = HEADERS
        response = requests.post(
            url, headers=headers, data=data, params=params, timeout=self.__timeout
        )
        # 404 resets the sid, session counters
        # 400 in session probably means bad sid
        # If user did a bad request (eg. remove an non-existing video from queue)
        # bind restores the session.
        if response.status_code in (404, 400) and session_request:
            self._bind()
        response.raise_for_status()
        if session_request:
            self._req_count += 1
        self._rid += 1
        return response


class YouTubeController(QuickPlayController):
    """Controller to interact with Youtube."""

    _session: YouTubeSession
    _screen_id: str | None = None

    def __init__(self, timeout: float = 10) -> None:
        super().__init__(YOUTUBE_NAMESPACE, APP_YOUTUBE)
        self.status_update_event = threading.Event()
        self._timeout = timeout

    def start_session_if_none(self) -> None:
        """
        Starts a session it is not yet initialized.
        """
        if not (self._screen_id and self._session):
            self.update_screen_id()
            self._session = TimeoutYouTubeSession(
                screen_id=cast(str, self._screen_id), timeout=self._timeout
            )

    def play_video(self, video_id: str, playlist_id: str | None = None) -> None:
        """
        Play video(video_id) now. This ignores the current play queue order.
        :param video_id: YouTube video id(http://youtube.com/watch?v=video_id)
        :param playlist_id: youtube.com/watch?v=video_id&list=playlist_id
        """
        self.start_session_if_none()
        self._session.play_video(video_id, playlist_id)

    def add_to_queue(self, video_id: str) -> None:
        """
        Add video(video_id) to the end of the play queue.
        :param video_id: YouTube video id(http://youtube.com/watch?v=video_id)
        """
        self.start_session_if_none()
        self._session.add_to_queue(video_id)

    def play_next(self, video_id: str) -> None:
        """
        Play video(video_id) after the currently playing video.
        :param video_id: YouTube video id(http://youtube.com/watch?v=video_id)
        """
        self.start_session_if_none()
        self._session.play_next(video_id)

    def remove_video(self, video_id: str) -> None:
        """
        Remove video(videoId) from the queue.
        :param video_id: YouTube video id(http://youtube.com/watch?v=video_id)
        """
        self.start_session_if_none()
        self._session.remove_video(video_id)

    def clear_playlist(self) -> None:
        """
        Clear the entire video queue
        """
        self.start_session_if_none()
        self._session.clear_playlist()

    def update_screen_id(self) -> None:
        """
        Sends a getMdxSessionStatus to get the screenId and waits for response.
        This function is blocking
        If connected we should always get a response
        (send message will launch app if it is not running).
        """
        self.status_update_event.clear()
        self.send_message({MESSAGE_TYPE: TYPE_GET_SCREEN_ID})
        status = self.status_update_event.wait(10)
        if not status:
            _LOGGER.warning("Failed to update screen_id")
        self.status_update_event.clear()

    def receive_message(self, _message: CastMessage, data: dict) -> bool:
        """Called when a message is received."""
        if data[MESSAGE_TYPE] == TYPE_STATUS:
            # Ignore the type error until validation of messages has been implemented
            self._process_status(data.get("data"))  # type: ignore[arg-type]
            return True

        return False

    def _process_status(self, status: dict) -> None:
        """Process latest status update."""
        self._screen_id = status.get(ATTR_SCREEN_ID)
        self.status_update_event.set()

    def quick_play(
        self,
        *,
        media_id: str,
        timeout: float,
        playlist_id: str | None = None,
        enqueue: bool = False,
        **kwargs: Any,
    ) -> None:
        """Quick Play"""
        self._timeout = timeout

        try:
            if enqueue:
                self.add_to_queue(media_id, **kwargs)
            else:
                self.play_video(media_id, playlist_id=playlist_id, **kwargs)
        except requests.Timeout as exc:
            raise RequestTimeout(f"youtube quick play {media_id}", timeout) from exc
