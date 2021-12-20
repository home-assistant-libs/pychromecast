"""
Provides a controller for controlling the default media players
on the Chromecast.
"""
import abc
from datetime import datetime
import logging

from collections import namedtuple
import threading

from ..config import APP_MEDIA_RECEIVER
from ..const import MESSAGE_TYPE
from ..error import PyChromecastError
from . import BaseController

STREAM_TYPE_UNKNOWN = "UNKNOWN"
STREAM_TYPE_BUFFERED = "BUFFERED"
STREAM_TYPE_LIVE = "LIVE"

MEDIA_PLAYER_STATE_PLAYING = "PLAYING"
MEDIA_PLAYER_STATE_BUFFERING = "BUFFERING"
MEDIA_PLAYER_STATE_PAUSED = "PAUSED"
MEDIA_PLAYER_STATE_IDLE = "IDLE"
MEDIA_PLAYER_STATE_UNKNOWN = "UNKNOWN"

TYPE_EDIT_TRACKS_INFO = "EDIT_TRACKS_INFO"
TYPE_GET_STATUS = "GET_STATUS"
TYPE_LOAD = "LOAD"
TYPE_QUEUE_INSERT = "QUEUE_INSERT"
TYPE_MEDIA_STATUS = "MEDIA_STATUS"
TYPE_PAUSE = "PAUSE"
TYPE_PLAY = "PLAY"
TYPE_QUEUE_NEXT = "QUEUE_NEXT"
TYPE_QUEUE_PREV = "QUEUE_PREV"
TYPE_QUEUE_UPDATE = "QUEUE_UPDATE"
TYPE_SEEK = "SEEK"
TYPE_STOP = "STOP"

METADATA_TYPE_GENERIC = 0
METADATA_TYPE_MOVIE = 1
METADATA_TYPE_TVSHOW = 2
METADATA_TYPE_MUSICTRACK = 3
METADATA_TYPE_PHOTO = 4

# From www.gstatic.com/cast/sdk/libs/caf_receiver/v3/cast_receiver_framework.js
CMD_SUPPORT_PAUSE = 1
CMD_SUPPORT_SEEK = 2
CMD_SUPPORT_STREAM_VOLUME = 4
CMD_SUPPORT_STREAM_MUTE = 8
# ALL_BASIC_MEDIA = PAUSE | SEEK | VOLUME | MUTE | EDIT_TRACKS | PLAYBACK_RATE
CMD_SUPPORT_ALL_BASIC_MEDIA = 12303
CMD_SUPPORT_QUEUE_NEXT = 64
CMD_SUPPORT_QUEUE_PREV = 128
CMD_SUPPORT_QUEUE_SHUFFLE = 256
CMD_SUPPORT_QUEUE_REPEAT_ALL = 1024
CMD_SUPPORT_QUEUE_REPEAT_ONE = 2048
CMD_SUPPORT_QUEUE_REPEAT = 3072
CMD_SUPPORT_SKIP_AD = 512
CMD_SUPPORT_EDIT_TRACKS = 4096
CMD_SUPPORT_PLAYBACK_RATE = 8192
CMD_SUPPORT_LIKE = 16384
CMD_SUPPORT_DISLIKE = 32768
CMD_SUPPORT_FOLLOW = 65536
CMD_SUPPORT_UNFOLLOW = 131072
CMD_SUPPORT_STREAM_TRANSFER = 262144

# Legacy?
CMD_SUPPORT_SKIP_FORWARD = 16
CMD_SUPPORT_SKIP_BACKWARD = 32


MediaImage = namedtuple("MediaImage", "url height width")

_LOGGER = logging.getLogger(__name__)


class MediaStatus:
    """Class to hold the media status."""

    def __init__(self):
        self.current_time = 0
        self.content_id = None
        self.content_type = None
        self.duration = None
        self.stream_type = STREAM_TYPE_UNKNOWN
        self.idle_reason = None
        self.media_session_id = None
        self.playback_rate = 1
        self.player_state = MEDIA_PLAYER_STATE_UNKNOWN
        self.supported_media_commands = 0
        self.volume_level = 1
        self.volume_muted = False
        self.media_custom_data = {}
        self.media_metadata = {}
        self.subtitle_tracks = {}
        self.current_subtitle_tracks = []
        self.last_updated = None

    @property
    def adjusted_current_time(self):
        """Returns calculated current seek time of media in seconds"""
        if self.player_state == MEDIA_PLAYER_STATE_PLAYING:
            # Add time since last update
            return (
                self.current_time
                + (datetime.utcnow() - self.last_updated).total_seconds()
            )
        # Not playing, return last reported seek time
        return self.current_time

    @property
    def metadata_type(self):
        """Type of meta data."""
        return self.media_metadata.get("metadataType")

    @property
    def player_is_playing(self):
        """Return True if player is PLAYING."""
        return self.player_state in (
            MEDIA_PLAYER_STATE_PLAYING,
            MEDIA_PLAYER_STATE_BUFFERING,
        )

    @property
    def player_is_paused(self):
        """Return True if player is PAUSED."""
        return self.player_state == MEDIA_PLAYER_STATE_PAUSED

    @property
    def player_is_idle(self):
        """Return True if player is IDLE."""
        return self.player_state == MEDIA_PLAYER_STATE_IDLE

    @property
    def media_is_generic(self):
        """Return True if media status represents generic media."""
        return self.metadata_type == METADATA_TYPE_GENERIC

    @property
    def media_is_tvshow(self):
        """Return True if media status represents a tv show."""
        return self.metadata_type == METADATA_TYPE_TVSHOW

    @property
    def media_is_movie(self):
        """Return True if media status represents a movie."""
        return self.metadata_type == METADATA_TYPE_MOVIE

    @property
    def media_is_musictrack(self):
        """Return True if media status represents a musictrack."""
        return self.metadata_type == METADATA_TYPE_MUSICTRACK

    @property
    def media_is_photo(self):
        """Return True if media status represents a photo."""
        return self.metadata_type == METADATA_TYPE_PHOTO

    @property
    def stream_type_is_buffered(self):
        """Return True if stream type is BUFFERED."""
        return self.stream_type == STREAM_TYPE_BUFFERED

    @property
    def stream_type_is_live(self):
        """Return True if stream type is LIVE."""
        return self.stream_type == STREAM_TYPE_LIVE

    @property
    def title(self):
        """Return title of media."""
        return self.media_metadata.get("title")

    @property
    def series_title(self):
        """Return series title if available."""
        return self.media_metadata.get("seriesTitle")

    @property
    def season(self):
        """Return season if available."""
        return self.media_metadata.get("season")

    @property
    def episode(self):
        """Return episode if available."""
        return self.media_metadata.get("episode")

    @property
    def artist(self):
        """Return artist if available."""
        return self.media_metadata.get("artist")

    @property
    def album_name(self):
        """Return album name if available."""
        return self.media_metadata.get("albumName")

    @property
    def album_artist(self):
        """Return album artist if available."""
        return self.media_metadata.get("albumArtist")

    @property
    def track(self):
        """Return track number if available."""
        return self.media_metadata.get("track")

    @property
    def images(self):
        """Return a list of MediaImage objects for this media."""
        return [
            MediaImage(item.get("url"), item.get("height"), item.get("width"))
            for item in self.media_metadata.get("images", [])
        ]

    @property
    def supports_pause(self):
        """True if PAUSE is supported."""
        return bool(self.supported_media_commands & CMD_SUPPORT_PAUSE)

    @property
    def supports_seek(self):
        """True if SEEK is supported."""
        return bool(self.supported_media_commands & CMD_SUPPORT_SEEK)

    @property
    def supports_stream_volume(self):
        """True if STREAM_VOLUME is supported."""
        return bool(self.supported_media_commands & CMD_SUPPORT_STREAM_VOLUME)

    @property
    def supports_stream_mute(self):
        """True if STREAM_MUTE is supported."""
        return bool(self.supported_media_commands & CMD_SUPPORT_STREAM_MUTE)

    @property
    def supports_skip_forward(self):
        """True if SKIP_FORWARD is supported."""
        return bool(self.supported_media_commands & CMD_SUPPORT_SKIP_FORWARD)

    @property
    def supports_skip_backward(self):
        """True if SKIP_BACKWARD is supported."""
        return bool(self.supported_media_commands & CMD_SUPPORT_SKIP_BACKWARD)

    @property
    def supports_queue_next(self):
        """True if QUEUE_NEXT is supported."""
        return bool(self.supported_media_commands & CMD_SUPPORT_QUEUE_NEXT)

    @property
    def supports_queue_prev(self):
        """True if QUEUE_PREV is supported."""
        return bool(self.supported_media_commands & CMD_SUPPORT_QUEUE_PREV)

    def update(self, data):
        """New data will only contain the changed attributes."""
        if not data.get("status", []):
            return

        status_data = data["status"][0]
        media_data = status_data.get("media") or {}
        volume_data = status_data.get("volume", {})

        self.current_time = status_data.get("currentTime", self.current_time)
        self.content_id = media_data.get("contentId", self.content_id)
        self.content_type = media_data.get("contentType", self.content_type)
        self.duration = media_data.get("duration", self.duration)
        self.stream_type = media_data.get("streamType", self.stream_type)
        self.idle_reason = status_data.get("idleReason", self.idle_reason)
        self.media_session_id = status_data.get("mediaSessionId", self.media_session_id)
        self.playback_rate = status_data.get("playbackRate", self.playback_rate)
        self.player_state = status_data.get("playerState", self.player_state)
        self.supported_media_commands = status_data.get(
            "supportedMediaCommands", self.supported_media_commands
        )
        self.volume_level = volume_data.get("level", self.volume_level)
        self.volume_muted = volume_data.get("muted", self.volume_muted)
        self.media_custom_data = media_data.get("customData", self.media_custom_data)
        self.media_metadata = media_data.get("metadata", self.media_metadata)
        self.subtitle_tracks = media_data.get("tracks", self.subtitle_tracks)
        self.current_subtitle_tracks = status_data.get(
            "activeTrackIds", self.current_subtitle_tracks
        )
        self.last_updated = datetime.utcnow()

    def __repr__(self):
        info = {
            "metadata_type": self.metadata_type,
            "title": self.title,
            "series_title": self.series_title,
            "season": self.season,
            "episode": self.episode,
            "artist": self.artist,
            "album_name": self.album_name,
            "album_artist": self.album_artist,
            "track": self.track,
            "subtitle_tracks": self.subtitle_tracks,
            "images": self.images,
            "supports_pause": self.supports_pause,
            "supports_seek": self.supports_seek,
            "supports_stream_volume": self.supports_stream_volume,
            "supports_stream_mute": self.supports_stream_mute,
            "supports_skip_forward": self.supports_skip_forward,
            "supports_skip_backward": self.supports_skip_backward,
        }
        info.update(self.__dict__)
        return f"<MediaStatus {info}>"


class MediaStatusListener(abc.ABC):
    """Listener for receiving media status events."""

    @abc.abstractmethod
    def new_media_status(self, status: MediaStatus):
        """Updated media status."""


class MediaController(BaseController):
    """Controller to interact with Google media namespace."""

    def __init__(self):
        super().__init__("urn:x-cast:com.google.cast.media")

        self.media_session_id = 0
        self.status = MediaStatus()
        self.session_active_event = threading.Event()
        self._start_play_media_sent = threading.Event()
        self.app_id = APP_MEDIA_RECEIVER
        self._status_listeners = []

    def channel_connected(self):
        """Called when media channel is connected. Will update status."""
        self.update_status()

    def channel_disconnected(self):
        """Called when a media channel is disconnected. Will erase status."""
        self.status = MediaStatus()
        self._fire_status_changed()

    def receive_message(self, _message, data: dict):
        """Called when a media message is received."""
        if data[MESSAGE_TYPE] == TYPE_MEDIA_STATUS:
            self._process_media_status(data)

            return True

        return False

    def register_status_listener(self, listener: MediaStatusListener):
        """Register a listener for new media statuses. A new status will
        call listener.new_media_status(status)"""
        self._status_listeners.append(listener)

    def update_status(self, callback_function_param=False):
        """Send message to update the status."""
        self.send_message(
            {MESSAGE_TYPE: TYPE_GET_STATUS}, callback_function=callback_function_param
        )

    def _send_command(self, command):
        """Send a command to the Chromecast on media channel."""
        if self.status is None or self.status.media_session_id is None:
            self.logger.warning(
                "%s command requested but no session is active.", command[MESSAGE_TYPE]
            )
            return

        command["mediaSessionId"] = self.status.media_session_id

        self.send_message(command, inc_session_id=True)

    @property
    def is_playing(self):
        """Deprecated as of June 8, 2015. Use self.status.player_is_playing.
        Returns if the Chromecast is playing."""
        return self.status is not None and self.status.player_is_playing

    @property
    def is_paused(self):
        """Deprecated as of June 8, 2015. Use self.status.player_is_paused.
        Returns if the Chromecast is paused."""
        return self.status is not None and self.status.player_is_paused

    @property
    def is_idle(self):
        """Deprecated as of June 8, 2015. Use self.status.player_is_idle.
        Returns if the Chromecast is idle on a media supported app."""
        return self.status is not None and self.status.player_is_idle

    @property
    def title(self):
        """Deprecated as of June 8, 2015. Use self.status.title.
        Return title of the current playing item."""
        return None if not self.status else self.status.title

    @property
    def thumbnail(self):
        """Deprecated as of June 8, 2015. Use self.status.images.
        Return thumbnail url of current playing item."""
        if not self.status:
            return None

        images = self.status.images

        return images[0].url if images else None

    def play(self):
        """Send the PLAY command."""
        self._send_command({MESSAGE_TYPE: TYPE_PLAY})

    def pause(self):
        """Send the PAUSE command."""
        self._send_command({MESSAGE_TYPE: TYPE_PAUSE})

    def stop(self):
        """Send the STOP command."""
        self._send_command({MESSAGE_TYPE: TYPE_STOP})

    def rewind(self):
        """Starts playing the media from the beginning."""
        self.seek(0)

    def skip(self):
        """Skips rest of the media. Values less then -5 behaved flaky."""
        self.seek(int(self.status.duration) - 5)

    def seek(self, position):
        """Seek the media to a specific location."""
        self._send_command(
            {
                MESSAGE_TYPE: TYPE_SEEK,
                "currentTime": position,
                "resumeState": "PLAYBACK_START",
            }
        )

    def queue_next(self):
        """Send the QUEUE_NEXT command."""
        self._send_command({MESSAGE_TYPE: TYPE_QUEUE_UPDATE, "jump": 1})

    def queue_prev(self):
        """Send the QUEUE_PREV command."""
        self._send_command({MESSAGE_TYPE: TYPE_QUEUE_UPDATE, "jump": -1})

    def enable_subtitle(self, track_id):
        """Enable specific text track."""
        self._send_command(
            {MESSAGE_TYPE: TYPE_EDIT_TRACKS_INFO, "activeTrackIds": [track_id]}
        )

    def disable_subtitle(self):
        """Disable subtitle."""
        self._send_command({MESSAGE_TYPE: TYPE_EDIT_TRACKS_INFO, "activeTrackIds": []})

    def block_until_active(self, timeout=None):
        """
        Blocks thread until the media controller session is active on the
        chromecast. The media controller only accepts playback control
        commands when a media session is active.

        If a session is already active then the method returns immediately.

        :param timeout: a floating point number specifying a timeout for the
                        operation in seconds (or fractions thereof). Or None
                        to block forever.
        """
        self.session_active_event.wait(timeout=timeout)

    def _process_media_status(self, data):
        """Processes a STATUS message."""
        self.status.update(data)

        self.logger.debug("Media:Received status %s", data)

        # Update session active threading event
        if self.status.media_session_id is None:
            self.session_active_event.clear()
        else:
            self.session_active_event.set()

        self._fire_status_changed()

    def _fire_status_changed(self):
        """Tells listeners of a changed status."""
        for listener in self._status_listeners:
            try:
                listener.new_media_status(self.status)
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Exception thrown when calling media status callback")

    def play_media(  # pylint: disable=too-many-locals
        self,
        url,
        content_type,
        title=None,
        thumb=None,
        current_time=None,
        autoplay=True,
        stream_type=STREAM_TYPE_BUFFERED,
        metadata=None,
        subtitles=None,
        subtitles_lang="en-US",
        subtitles_mime="text/vtt",
        subtitle_id=1,
        enqueue=False,
        media_info=None,
    ):
        """
        Plays media on the Chromecast. Start default media receiver if not
        already started.

        Parameters:
        url: str - url of the media.
        content_type: str - mime type. Example: 'video/mp4'.
        title: str - title of the media.
        thumb: str - thumbnail image url.
        current_time: float - Seconds since beginning of content. If the content is
            live content, and position is not specifed, the stream will start at the
            live position
        autoplay: bool - whether the media will automatically play.
        stream_type: str - describes the type of media artifact as one of the
            following: "NONE", "BUFFERED", "LIVE".
        subtitles: str - url of subtitle file to be shown on chromecast.
        subtitles_lang: str - language for subtitles.
        subtitles_mime: str - mimetype of subtitles.
        subtitle_id: int - id of subtitle to be loaded.
        enqueue: bool - if True, enqueue the media instead of play it.
        media_info: dict - additional MediaInformation attributes not explicitly listed.
        metadata: dict - media metadata object, one of the following:
            GenericMediaMetadata, MovieMediaMetadata, TvShowMediaMetadata,
            MusicTrackMediaMetadata, PhotoMediaMetadata.

        Docs:
        https://developers.google.com/cast/docs/reference/messages#MediaData
        https://developers.google.com/cast/docs/reference/web_receiver/cast.framework.messages.MediaInformation
        """

        def app_launched_callback():
            """Plays media after chromecast has switched to requested app."""
            self._send_start_play_media(
                url,
                content_type,
                title,
                thumb,
                current_time,
                autoplay,
                stream_type,
                metadata,
                subtitles,
                subtitles_lang,
                subtitles_mime,
                subtitle_id,
                enqueue,
                media_info,
            )
            self._start_play_media_sent.set()

        self._start_play_media_sent.clear()
        receiver_ctrl = self._socket_client.receiver_controller
        receiver_ctrl.launch_app(self.app_id, callback_function=app_launched_callback)
        self._start_play_media_sent.wait(10)
        if not self._start_play_media_sent.is_set():
            raise PyChromecastError()

    def _send_start_play_media(  # pylint: disable=too-many-locals
        self,
        url,
        content_type,
        title=None,
        thumb=None,
        current_time=None,
        autoplay=True,
        stream_type=STREAM_TYPE_BUFFERED,
        metadata=None,
        subtitles=None,
        subtitles_lang="en-US",
        subtitles_mime="text/vtt",
        subtitle_id=1,
        enqueue=False,
        media_info=None,
    ):
        media_info = media_info or {}
        media = {
            "contentId": url,
            "streamType": stream_type,
            "contentType": content_type,
            "metadata": metadata or {},
            **media_info,
        }

        if title:
            media["metadata"]["title"] = title

        if thumb:
            media["metadata"]["thumb"] = thumb

            if "images" not in media["metadata"]:
                media["metadata"]["images"] = []

            media["metadata"]["images"].append({"url": thumb})

        # Need to set metadataType if not specified
        # https://developers.google.com/cast/docs/reference/messages#MediaInformation
        if media["metadata"] and "metadataType" not in media["metadata"]:
            media["metadata"]["metadataType"] = METADATA_TYPE_GENERIC

        if subtitles:
            sub_msg = [
                {
                    "trackId": subtitle_id,
                    "trackContentId": subtitles,
                    "language": subtitles_lang,
                    "subtype": "SUBTITLES",
                    "type": "TEXT",
                    "trackContentType": subtitles_mime,
                    "name": f"{subtitles_lang} - {subtitle_id} Subtitle",
                }
            ]
            media["tracks"] = sub_msg
            media["textTrackStyle"] = {
                "backgroundColor": "#FFFFFF00",
                "edgeType": "OUTLINE",
                "edgeColor": "#000000FF",
            }

        if enqueue:
            msg = {
                "mediaSessionId": self.status.media_session_id,
                "items": [
                    {
                        "media": media,
                        "autoplay": True,
                        "startTime": 0,
                        "preloadTime": 0,
                    }
                ],
                MESSAGE_TYPE: TYPE_QUEUE_INSERT,
            }
        else:
            msg = {
                "media": media,
                MESSAGE_TYPE: TYPE_LOAD,
            }
        if current_time is not None:
            msg["currentTime"] = current_time
        msg["autoplay"] = autoplay
        msg["customData"] = {}

        if subtitles:
            msg["activeTrackIds"] = [subtitle_id]

        self.send_message(msg, inc_session_id=True)

    def tear_down(self):
        """Called when controller is destroyed."""
        super().tear_down()

        self._status_listeners[:] = []

    def quick_play(self, media_id=None, media_type="video/mp4", **kwargs):
        """Quick Play"""
        self.play_media(media_id, media_type, **kwargs)
