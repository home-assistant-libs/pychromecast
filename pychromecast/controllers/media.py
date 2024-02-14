"""
Provides a controller for controlling the default media players
on the Chromecast.
"""

import abc
from datetime import datetime
from dataclasses import dataclass
import logging
import threading
from typing import Any

from ..config import APP_MEDIA_RECEIVER
from ..const import MESSAGE_TYPE
from ..error import ControllerNotRegistered
from ..generated.cast_channel_pb2 import (  # pylint: disable=no-name-in-module
    CastMessage,
)
from ..response_handler import WaitResponse
from . import CallbackType, QuickPlayController

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
TYPE_LOAD_FAILED = "LOAD_FAILED"
TYPE_QUEUE_INSERT = "QUEUE_INSERT"
TYPE_MEDIA_STATUS = "MEDIA_STATUS"
TYPE_PAUSE = "PAUSE"
TYPE_PLAY = "PLAY"
TYPE_QUEUE_NEXT = "QUEUE_NEXT"
TYPE_QUEUE_PREV = "QUEUE_PREV"
TYPE_QUEUE_UPDATE = "QUEUE_UPDATE"
TYPE_SEEK = "SEEK"
TYPE_SET_PLAYBACK_RATE = "SET_PLAYBACK_RATE"
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

# From https://developers.google.com/cast/docs/web_receiver/error_codes
MEDIA_PLAYER_ERROR_CODES: dict[int | None, str] = {
    100: "MEDIA_UNKNOWN",
    101: "MEDIA_ABORTED",
    102: "MEDIA_DECODE",
    103: "MEDIA_NETWORK",
    104: "MEDIA_SRC_NOT_SUPPORTED",
    110: "SOURCE_BUFFER_FAILURE",
    201: "MEDIAKEYS_NETWORK",
    202: "MEDIAKEYS_UNSUPPORTED",
    203: "MEDIAKEYS_WEBCRYPTO",
    301: "SEGMENT_NETWORK",
    311: "HLS_NETWORK_MASTER_PLAYLIST",
    312: "HLS_NETWORK_PLAYLIST",
    313: "HLS_NETWORK_NO_KEY_RESPONSE",
    314: "HLS_NETWORK_KEY_LOAD",
    315: "HLS_NETWORK_INVALID_SEGMENT",
    316: "HLS_SEGMENT_PARSING",
    321: "DASH_NETWORK",
    322: "DASH_NO_INIT",
    331: "SMOOTH_NETWORK",
    332: "SMOOTH_NO_MEDIA_DATA",
    411: "HLS_MANIFEST_MASTER",
    412: "HLS_MANIFEST_PLAYLIST",
    421: "DASH_MANIFEST_NO_PERIODS",
    422: "DASH_MANIFEST_NO_MIMETYPE",
    423: "DASH_INVALID_SEGMENT_INFO",
    431: "SMOOTH_MANIFEST",
}


@dataclass(frozen=True)
class MediaImage:
    """Media image metadata container."""

    url: str | None
    height: int | None
    width: int | None


_LOGGER = logging.getLogger(__name__)


class MediaStatus:
    """Class to hold the media status."""

    def __init__(self) -> None:
        self.current_time = 0.0
        self.content_id: str | None = None
        self.content_type: str | None = None
        self.duration: float | None = None
        self.stream_type = STREAM_TYPE_UNKNOWN
        self.idle_reason: str | None = None
        self.media_session_id: int | None = None
        self.playback_rate = 1.0
        self.player_state = MEDIA_PLAYER_STATE_UNKNOWN
        self.supported_media_commands = 0
        self.volume_level = 1.0
        self.volume_muted = False
        self.media_custom_data: dict = {}
        self.media_metadata: dict = {}
        self.subtitle_tracks: dict = {}
        self.current_subtitle_tracks: list = []
        self.last_updated: datetime | None = None

    @property
    def adjusted_current_time(self) -> float | None:
        """Returns calculated current seek time of media in seconds"""
        if (
            self.current_time is not None
            and self.last_updated is not None
            and self.player_state == MEDIA_PLAYER_STATE_PLAYING
        ):
            # Add time since last update
            return (
                self.current_time
                + self.playback_rate
                * (datetime.utcnow() - self.last_updated).total_seconds()
            )
        # Not playing, return last reported seek time
        return self.current_time

    @property
    def metadata_type(self) -> int | None:
        """Type of meta data."""
        return self.media_metadata.get("metadataType")

    @property
    def player_is_playing(self) -> bool:
        """Return True if player is PLAYING."""
        return self.player_state in (
            MEDIA_PLAYER_STATE_PLAYING,
            MEDIA_PLAYER_STATE_BUFFERING,
        )

    @property
    def player_is_paused(self) -> bool:
        """Return True if player is PAUSED."""
        return self.player_state == MEDIA_PLAYER_STATE_PAUSED

    @property
    def player_is_idle(self) -> bool:
        """Return True if player is IDLE."""
        return self.player_state == MEDIA_PLAYER_STATE_IDLE

    @property
    def media_is_generic(self) -> bool:
        """Return True if media status represents generic media."""
        return self.metadata_type == METADATA_TYPE_GENERIC

    @property
    def media_is_tvshow(self) -> bool:
        """Return True if media status represents a tv show."""
        return self.metadata_type == METADATA_TYPE_TVSHOW

    @property
    def media_is_movie(self) -> bool:
        """Return True if media status represents a movie."""
        return self.metadata_type == METADATA_TYPE_MOVIE

    @property
    def media_is_musictrack(self) -> bool:
        """Return True if media status represents a musictrack."""
        return self.metadata_type == METADATA_TYPE_MUSICTRACK

    @property
    def media_is_photo(self) -> bool:
        """Return True if media status represents a photo."""
        return self.metadata_type == METADATA_TYPE_PHOTO

    @property
    def stream_type_is_buffered(self) -> bool:
        """Return True if stream type is BUFFERED."""
        return self.stream_type == STREAM_TYPE_BUFFERED

    @property
    def stream_type_is_live(self) -> bool:
        """Return True if stream type is LIVE."""
        return self.stream_type == STREAM_TYPE_LIVE

    @property
    def title(self) -> str | None:
        """Return title of media."""
        return self.media_metadata.get("title")

    @property
    def series_title(self) -> str | None:
        """Return series title if available."""
        return self.media_metadata.get("seriesTitle")

    @property
    def season(self) -> int | None:
        """Return season if available."""
        return self.media_metadata.get("season")

    @property
    def episode(self) -> int | None:
        """Return episode if available."""
        return self.media_metadata.get("episode")

    @property
    def artist(self) -> str | None:
        """Return artist if available."""
        return self.media_metadata.get("artist")

    @property
    def album_name(self) -> str | None:
        """Return album name if available."""
        return self.media_metadata.get("albumName")

    @property
    def album_artist(self) -> str | None:
        """Return album artist if available."""
        return self.media_metadata.get("albumArtist")

    @property
    def track(self) -> int | None:
        """Return track number if available."""
        return self.media_metadata.get("track")

    @property
    def images(self) -> list[MediaImage]:
        """Return a list of MediaImage objects for this media."""
        return [
            MediaImage(item.get("url"), item.get("height"), item.get("width"))
            for item in self.media_metadata.get("images", [])
        ]

    @property
    def supports_pause(self) -> bool:
        """True if PAUSE is supported."""
        return bool(self.supported_media_commands & CMD_SUPPORT_PAUSE)

    @property
    def supports_seek(self) -> bool:
        """True if SEEK is supported."""
        return bool(self.supported_media_commands & CMD_SUPPORT_SEEK)

    @property
    def supports_stream_volume(self) -> bool:
        """True if STREAM_VOLUME is supported."""
        return bool(self.supported_media_commands & CMD_SUPPORT_STREAM_VOLUME)

    @property
    def supports_stream_mute(self) -> bool:
        """True if STREAM_MUTE is supported."""
        return bool(self.supported_media_commands & CMD_SUPPORT_STREAM_MUTE)

    @property
    def supports_skip_forward(self) -> bool:
        """True if SKIP_FORWARD is supported."""
        return bool(self.supported_media_commands & CMD_SUPPORT_SKIP_FORWARD)

    @property
    def supports_skip_backward(self) -> bool:
        """True if SKIP_BACKWARD is supported."""
        return bool(self.supported_media_commands & CMD_SUPPORT_SKIP_BACKWARD)

    @property
    def supports_queue_next(self) -> bool:
        """True if QUEUE_NEXT is supported."""
        return bool(self.supported_media_commands & CMD_SUPPORT_QUEUE_NEXT)

    @property
    def supports_queue_prev(self) -> bool:
        """True if QUEUE_PREV is supported."""
        return bool(self.supported_media_commands & CMD_SUPPORT_QUEUE_PREV)

    def update(self, data: dict) -> None:
        """New data will only contain the changed attributes."""
        if not data.get("status", []):
            return

        status_data = data["status"][0]
        media_data = status_data.get("media") or {}
        if not media_data and "extendedStatus" in status_data:
            media_data = status_data["extendedStatus"].get("media") or {}
        volume_data = status_data.get("volume", {})

        self.current_time = status_data.get("currentTime", self.current_time)
        self.content_id = media_data.get("contentId", self.content_id)
        self.content_type = media_data.get("contentType", self.content_type)
        self.duration = media_data.get("duration", self.duration)
        self.stream_type = media_data.get("streamType", self.stream_type)
        # Clear idle reason if not set in the message
        self.idle_reason = status_data.get("idleReason", None)
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

    def __repr__(self) -> str:
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
    def new_media_status(self, status: MediaStatus) -> None:
        """Updated media status."""

    @abc.abstractmethod
    def load_media_failed(self, queue_item_id: int, error_code: int) -> None:
        """Called when load media failed.

        queue_item_id is the id of the queue item which failed to load
        """


class BaseMediaPlayer(QuickPlayController):
    """Mixin class for apps which can play media using the default media namespace."""

    def __init__(self, supporting_app_id: str, app_must_match: bool = True) -> None:
        super().__init__(
            "urn:x-cast:com.google.cast.media",
            supporting_app_id=supporting_app_id,
            app_must_match=app_must_match,
        )

    def play_media(  # pylint: disable=too-many-locals
        self,
        url: str,
        content_type: str,
        *,
        title: str | None = None,
        thumb: str | None = None,
        current_time: float | None = None,
        autoplay: bool = True,
        stream_type: str = STREAM_TYPE_LIVE,
        metadata: dict | None = None,
        subtitles: str | None = None,
        subtitles_lang: str = "en-US",
        subtitles_mime: str = "text/vtt",
        subtitle_id: int = 1,
        enqueue: bool = False,
        media_info: dict | None = None,
        callback_function: CallbackType | None = None,
    ) -> None:
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
            callback_function=callback_function,
        )

    def _send_start_play_media(  # pylint: disable=too-many-locals
        self,
        url: str,
        content_type: str,
        title: str | None,
        thumb: str | None,
        current_time: float | None,
        autoplay: bool,
        stream_type: str,
        metadata: dict | None,
        subtitles: str | None,
        subtitles_lang: str,
        subtitles_mime: str,
        subtitle_id: int,
        enqueue: bool,
        media_info: dict | None,
        callback_function: CallbackType | None,
    ) -> None:
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
            if self._socket_client is None:
                raise ControllerNotRegistered
            status = self._socket_client.media_controller.status
            msg: dict[str, Any] = {
                "mediaSessionId": status.media_session_id,
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

        self.send_message(msg, inc_session_id=True, callback_function=callback_function)

    def quick_play(self, *, media_id: str, timeout: float, **kwargs: Any) -> None:
        """Quick Play"""

        media_type = kwargs.pop("media_type", "video/mp4")

        response_handler = WaitResponse(timeout, f"quick play {media_id}")
        self.play_media(
            media_id, media_type, **kwargs, callback_function=response_handler.callback
        )
        response_handler.wait_response()


class MediaController(BaseMediaPlayer):
    """Controller to interact with Google media namespace."""

    def __init__(self) -> None:
        super().__init__(
            supporting_app_id=APP_MEDIA_RECEIVER,
            app_must_match=False,
        )

        self.media_session_id = 0
        self.status = MediaStatus()
        self.session_active_event = threading.Event()
        self._status_listeners: list[MediaStatusListener] = []

    def channel_connected(self) -> None:
        """Called when media channel is connected. Will update status."""
        self.update_status()

    def channel_disconnected(self) -> None:
        """Called when a media channel is disconnected. Will erase status."""
        self.status = MediaStatus()
        self._fire_status_changed()

    def receive_message(self, _message: CastMessage, data: dict) -> bool:
        """Called when a media message is received."""
        if data[MESSAGE_TYPE] == TYPE_MEDIA_STATUS:
            self._process_media_status(data)
            return True
        if data[MESSAGE_TYPE] == TYPE_LOAD_FAILED:
            self._process_load_failed(data)

            return True

        return False

    def register_status_listener(self, listener: MediaStatusListener) -> None:
        """Register a listener for new media statuses. A new status will
        call listener.new_media_status(status)"""
        self._status_listeners.append(listener)

    def update_status(self, *, callback_function: CallbackType | None = None) -> None:
        """Send message to update the status."""
        self.send_message(
            {MESSAGE_TYPE: TYPE_GET_STATUS}, callback_function=callback_function
        )

    def _send_command(
        self, command: dict, callback_function: CallbackType | None
    ) -> None:
        """Send a command to the Chromecast on media channel."""
        if self.status is None or self.status.media_session_id is None:
            self.logger.warning(
                "%s command requested but no session is active.", command[MESSAGE_TYPE]
            )
            if callback_function:
                callback_function(False, None)
            return

        command["mediaSessionId"] = self.status.media_session_id

        self.send_message(
            command, callback_function=callback_function, inc_session_id=True
        )

    def play(self, timeout: float = 10.0) -> None:
        """Send the PLAY command."""
        response_handler = WaitResponse(timeout, "play")
        self._send_command({MESSAGE_TYPE: TYPE_PLAY}, response_handler.callback)
        response_handler.wait_response()

    def pause(self, timeout: float = 10.0) -> None:
        """Send the PAUSE command."""
        response_handler = WaitResponse(timeout, "pause")
        self._send_command({MESSAGE_TYPE: TYPE_PAUSE}, response_handler.callback)
        response_handler.wait_response()

    def stop(self, timeout: float = 10.0) -> None:
        """Send the STOP command."""
        response_handler = WaitResponse(timeout, "stop")
        self._send_command({MESSAGE_TYPE: TYPE_STOP}, response_handler.callback)
        response_handler.wait_response()

    def rewind(self, timeout: float = 10.0) -> None:
        """Starts playing the media from the beginning."""
        self.seek(0, timeout)

    def skip(self, timeout: float = 10.0) -> None:
        """Skips rest of the media. Values less then -5 behaved flaky."""
        if not self.status.duration or self.status.duration < 5:
            return
        self.seek(int(self.status.duration) - 5, timeout)

    def seek(self, position: float, timeout: float = 10.0) -> None:
        """Seek the media to a specific location."""
        response_handler = WaitResponse(timeout, f"seek {position}")
        self._send_command(
            {
                MESSAGE_TYPE: TYPE_SEEK,
                "currentTime": position,
                "resumeState": "PLAYBACK_START",
            },
            response_handler.callback,
        )
        response_handler.wait_response()

    def set_playback_rate(self, playback_rate: float, timeout: float = 10.0) -> None:
        """Set the playback rate. 1.0 is regular time, 0.5 is slow motion."""
        response_handler = WaitResponse(timeout, "set playback rate")
        self._send_command(
            {
                MESSAGE_TYPE: TYPE_SET_PLAYBACK_RATE,
                "playbackRate": playback_rate,
            },
            response_handler.callback,
        )
        response_handler.wait_response()

    def queue_next(self, timeout: float = 10.0) -> None:
        """Send the QUEUE_NEXT command."""
        response_handler = WaitResponse(timeout, "queue next")
        self._send_command(
            {MESSAGE_TYPE: TYPE_QUEUE_UPDATE, "jump": 1}, response_handler.callback
        )
        response_handler.wait_response()

    def queue_prev(self, timeout: float = 10.0) -> None:
        """Send the QUEUE_PREV command."""
        response_handler = WaitResponse(timeout, "queue prev")
        self._send_command(
            {MESSAGE_TYPE: TYPE_QUEUE_UPDATE, "jump": -1}, response_handler.callback
        )
        response_handler.wait_response()

    def enable_subtitle(self, track_id: int, timeout: float = 10.0) -> None:
        """Enable specific text track."""
        response_handler = WaitResponse(timeout, "enable subtitle")
        self._send_command(
            {MESSAGE_TYPE: TYPE_EDIT_TRACKS_INFO, "activeTrackIds": [track_id]},
            response_handler.callback,
        )
        response_handler.wait_response()

    def disable_subtitle(self, timeout: float = 10.0) -> None:
        """Disable subtitle."""
        response_handler = WaitResponse(timeout, "disable subtitle")
        self._send_command(
            {MESSAGE_TYPE: TYPE_EDIT_TRACKS_INFO, "activeTrackIds": []},
            response_handler.callback,
        )
        response_handler.wait_response()

    def block_until_active(self, timeout: float | None = None) -> None:
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

    def _process_media_status(self, data: dict) -> None:
        """Processes a STATUS message."""
        self.status.update(data)

        self.logger.debug("Media:Updated status %s", self.status)

        # Update session active threading event
        if self.status.media_session_id is None:
            self.session_active_event.clear()
        else:
            self.session_active_event.set()

        self._fire_status_changed()

    def _process_load_failed(self, data: dict) -> None:
        """Processes a LOAD_FAILED message."""
        queue_item_id: int | None = data.get("itemId")
        error_code: int | None = data.get("detailedErrorCode")

        self.logger.debug(
            "Media:Load failed with code %s(%s) for queue item id %s",
            error_code,
            MEDIA_PLAYER_ERROR_CODES.get(error_code, "unknown code"),
            queue_item_id,
        )

        if queue_item_id is None or error_code is None:
            self.logger.debug("Media:Not firing load failed")
            return

        self._fire_load_failed(queue_item_id, error_code)

    def _fire_status_changed(self) -> None:
        """Tells listeners of a changed status."""
        for listener in self._status_listeners:
            try:
                listener.new_media_status(self.status)
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Exception thrown when calling media status callback")

    def _fire_load_failed(self, queue_item_id: int, error_code: int) -> None:
        """Tells listeners of a changed status."""
        for listener in self._status_listeners:
            try:
                listener.load_media_failed(queue_item_id, error_code)
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Exception thrown when calling load failed callback")

    def tear_down(self) -> None:
        """Called when controller is destroyed."""
        super().tear_down()

        self._status_listeners = []


class DefaultMediaReceiverController(BaseMediaPlayer):
    """Controller to force media to play with the default media receiver."""

    def __init__(self) -> None:
        super().__init__(supporting_app_id=APP_MEDIA_RECEIVER)
