"""
Controller to interface with the YouTube-app.
Use the media controller to play, pause etc.
"""
import re
import threading
from json import JSONDecodeError

import requests
from . import BaseController
from ..error import UnsupportedNamespace

YOUTUBE_BASE_URL = "https://www.youtube.com/"
BIND_URL = YOUTUBE_BASE_URL + "api/lounge/bc/bind"
LOUNGE_TOKEN_URL = YOUTUBE_BASE_URL + "api/lounge/pairing/get_lounge_token_batch"

HEADERS = {"Origin": YOUTUBE_BASE_URL, "Content-Type": "application/x-www-form-urlencoded"}
LOUNGE_ID_HEADER = "X-YouTube-LoungeId-Token"
REQ_PREFIX = "req{req_id}"

GSESSION_ID_REGEX = '"S","(.*?)"]'
SID_REGEX = '"c","(.*?)",\"'

CURRENT_INDEX = '_currentIndex'
CURRENT_TIME = '_currentTime'
AUDIO_ONLY = '_audioOnly'
VIDEO_ID = '_videoId'
LIST_ID = "_listId"
ACTION = '__sc'
COUNT = 'count'

ACTION_SET_PLAYLIST = 'setPlaylist'
ACTION_REMOVE = 'removeVideo'
ACTION_INSERT = 'insertVideo'
ACTION_ADD = 'addVideo'

GSESSIONID = 'gsessionid'
CVER = 'CVER'
RID = 'RID'
SID = 'SID'
VER = 'VER'

TYPE_GET_SCREEN_ID = "getMdxSessionStatus"
TYPE_STATUS = "mdxSessionStatus"
ATTR_SCREEN_ID = "screenId"
MESSAGE_TYPE = "type"

BIND_DATA = {"device": "REMOTE_CONTROL", "id": 'aaaaaaaaaaaaaaaaaaaaaaaaaa', "name": "Python", "mdx-version": 3,
             'pairing_type': 'cast', 'app': 'android-phone-13.14.55'}


class YoutubeSessionError(Exception):
    pass


class YouTubeController(BaseController):
    """ Controller to interact with Youtube."""

    def __init__(self):
        super(YouTubeController, self).__init__(
            "urn:x-cast:com.google.youtube.mdx", "233637DE")
        self._lounge_token = None
        self._gsession_id = None
        self._screen_id = None
        self._sid = None
        self._rid = 0
        self._req_count = 0
        self.status_update_event = threading.Event()

    @property
    def in_session(self):
        """ Returns True if session params are not None."""
        if self._gsession_id and self._lounge_token:
            return True
        else:
            return False

    def play_video(self, video_id):
        """
        Play video(video_id) now. This ignores the current play queue order.
        :param video_id: YouTube video id(http://youtube.com/watch?v=video_id)
        """
        self._start_session()
        self._initialize_queue(video_id)

    def add_to_queue(self, video_id):
        """
        Add video(video_id) to the end of the play queue.
        :param video_id: YouTube video id(http://youtube.com/watch?v=video_id)
        """
        self._queue_action(video_id, ACTION_ADD)

    def play_next(self, video_id):
        """
        Play video(video_id) after the currently playing video.
        :param video_id: YouTube video id(http://youtube.com/watch?v=video_id)
        """
        self._queue_action(video_id, ACTION_INSERT)

    def remove_video(self, video_id):
        """
        Remove video(videoId) from the queue.
        :param video_id: YouTube video id(http://youtube.com/watch?v=video_id)
        """
        self._queue_action(video_id, ACTION_REMOVE)

    def _start_session(self):
        if not self._screen_id:
            self.update_screen_id()
        self._get_lounge_id()
        self._bind()

    def update_screen_id(self):
        """
        Sends a getMdxSessionStatus to get the screen id and waits for response.
        This function is blocking but if connected we should always get a response
        (send message will launch app if it is not running).
        """
        self.status_update_event.clear()
        # This gets the screenId but always throws. Couldn't find a better way.
        try:
            self.send_message({MESSAGE_TYPE: TYPE_GET_SCREEN_ID})
        except UnsupportedNamespace:
            pass
        self.status_update_event.wait()
        self.status_update_event.clear()

    def _get_lounge_id(self):
        """
        Get the lounge_token.
        The token is used as a header in all session requests.
        """
        data = {"screen_ids": self._screen_id}
        response = self._do_post(LOUNGE_TOKEN_URL, data=data)
        try:
            lounge_token = response.json()["screens"][0]["loungeToken"]
        except JSONDecodeError:
            raise YoutubeSessionError("Could not get lounge id.")
        self._lounge_token = lounge_token

    def _bind(self):
        """
        Bind to the app and get SID, gsessionid session identifiers.
        If the chromecast is already in another YouTube session you should get the SID, gsessionid for that session.
        SID, gsessionid are used as url params in all further session requests.
        """
        # reset session counters before starting a new session
        self._rid = 0
        self._req_count = 0

        url_params = {RID: self._rid, VER: 8, CVER: 1}
        response = self._do_post(BIND_URL, data=BIND_DATA, headers={LOUNGE_ID_HEADER: self._lounge_token},
                                 params=url_params)
        content = str(response.content)
        sid = re.search(SID_REGEX, content)
        gsessionid = re.search(GSESSION_ID_REGEX, content)
        if not (sid and gsessionid):
            raise YoutubeSessionError("Could not parse session parameters.")
        self._sid = sid.group(1)
        self._gsession_id = gsessionid.group(1)

    def _initialize_queue(self, video_id):
        """
        Initialize a queue with a video and start playing that video.
        """
        request_data = {LIST_ID: "",
                        ACTION: ACTION_SET_PLAYLIST,
                        CURRENT_TIME: '0',
                        CURRENT_INDEX: -1,
                        AUDIO_ONLY: 'false',
                        VIDEO_ID: video_id,
                        COUNT: 1, }

        request_data = self._format_session_params(request_data)
        url_params = {SID: self._sid, GSESSIONID: self._gsession_id, RID: self._rid, VER: 8, CVER: 1}
        self._do_post(BIND_URL, data=request_data, headers={LOUNGE_ID_HEADER: self._lounge_token},
                      session_request=True, params=url_params)

    def _queue_action(self, video_id, action):
        """
        Sends actions for an established queue.
        :param video_id: id to perform the action on
        :param action: the action to perform
        """
        # If nothing is playing actions will work but won't affect the queue. This is for binding existing sessions
        if not self.in_session:
            self._start_session()
        request_data = {ACTION: action,
                        VIDEO_ID: video_id,
                        COUNT: 1}
        request_data = self._format_session_params(request_data)
        url_params = {SID: self._sid, GSESSIONID: self._gsession_id, RID: self._rid, VER: 8, CVER: 1}
        self._do_post(BIND_URL, data=request_data, headers={LOUNGE_ID_HEADER: self._lounge_token},
                      session_request=True, params=url_params)

    def _format_session_params(self, param_dict):
        req_count = REQ_PREFIX.format(req_id=self._req_count)
        return {req_count + k if k.startswith('_') else k: v for k, v in param_dict.items()}

    def _do_post(self, url, data, params=None, headers=None, session_request=False):
        """
        Calls requests.post with custom headers, increments RID(request id) on every post.
        will raise if response is not 200
        :param url:(str) request url
        :param data: (dict) the POST body
        :param params:(dict) POST url params
        :param headers:(dict) Additional headers for the request
        :param session_request:(bool) True to increment session request counter(req_count)
        :return: POST response
        """
        if headers:
            headers = dict(**dict(HEADERS, **headers))
        else:
            headers = HEADERS
        response = requests.post(url, headers=headers, data=data, params=params)
        # 404 resets the sid, session counters
        # 400 in session probably means bad sid
        if (response.status_code == 404 or response.status_code == 400) and session_request:
            self._bind()
        response.raise_for_status()
        if session_request:
            self._req_count += 1
        self._rid += 1
        return response

    def receive_message(self, message, data):
        """ Called when a media message is received. """
        if data[MESSAGE_TYPE] == TYPE_STATUS:
            self._process_status(data.get("data"))

            return True

        else:
            return False

    def _process_status(self, status):
        """ Process latest status update. """
        self._screen_id = status.get(ATTR_SCREEN_ID)
        self.status_update_event.set()

    def tear_down(self):
        """ Called when controller is destroyed. """
        super(YouTubeController, self).tear_down()
        self._lounge_token = None
        self._gsession_id = None
        self._screen_id = None
        self._sid = None
        self._rid = 0
        self._req_count = 0
