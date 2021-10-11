"""
Controller to interface with the Plex-app.
"""
import json
import threading

from copy import deepcopy
from urllib.parse import urlparse

from . import BaseController
from ..const import MESSAGE_TYPE

STREAM_TYPE_UNKNOWN = "UNKNOWN"
STREAM_TYPE_BUFFERED = "BUFFERED"
STREAM_TYPE_LIVE = "LIVE"
SEEK_KEY = "currentTime"
TYPE_PLAY = "PLAY"
TYPE_PAUSE = "PAUSE"
TYPE_STOP = "STOP"
TYPE_STEPFORWARD = "STEPFORWARD"
TYPE_STEPBACKWARD = "STEPBACK"
TYPE_PREVIOUS = "PREVIOUS"
TYPE_NEXT = "NEXT"
TYPE_LOAD = "LOAD"
TYPE_DETAILS = "SHOWDETAILS"
TYPE_SEEK = "SEEK"
TYPE_MEDIA_STATUS = "MEDIA_STATUS"
TYPE_GET_STATUS = "GET_STATUS"
TYPE_EDIT_TRACKS_INFO = "EDIT_TRACKS_INFO"


def media_to_chromecast_command(
    media=None,
    type="LOAD",  # pylint: disable=redefined-builtin
    requestId=1,
    offset=0,
    directPlay=True,
    directStream=True,
    subtitleSize=100,
    audioBoost=100,
    transcoderVideo=True,
    transcoderVideoRemuxOnly=False,
    transcoderAudio=True,
    isVerifiedHostname=True,
    contentType="video",
    myPlexSubscription=True,
    contentId=None,
    streamType=STREAM_TYPE_BUFFERED,
    port=32400,
    protocol="http",
    address=None,
    username=None,
    autoplay=True,
    currentTime=0,
    playQueue=None,
    playQueueID=None,
    startItem=None,
    version="1.10.1.4602",
    **kwargs,
):  # pylint: disable=invalid-name, too-many-locals, protected-access
    """Create the message that chromecast requires. Use pass of plexapi media object or
       set all the needed kwargs manually. See the code for what to set.

    Args:
        media (None, optional): a :class:`~plexapi.base.Playable
        type (str): Default LOAD, SHOWDETAILS.
        requestId (int): The requestId, Chromecasts may use this.
        offset (int): Offset of the playback in seconds.
        directPlay (bool): Default True
        directStream (bool): Default True
        subtitleSize (int): Set the subtitle size, possibly only 100 & 200.
        audioBoost (int): Default 100
        transcoderVideo (bool): Default True
        transcoderVideoRemuxOnly (bool): Default False
        transcoderAudio (bool): Default True
        isVerifiedHostname (bool): Default True
        contentType (str): Default 'video', 'audio'
        myPlexSubscription (bool): True if user has a PlexPass.
        contentId (str): The key Chromecasts use to start playback.
        streamType (str): Default BUFFERED, LIVE
        port (int): PMS port
        address (str): PMS host, without scheme.
        username (None): Username of the user that started playback.
        autoplay (bool): Auto play after the video is done.
        currentTime (int): Set playback from this time. default 0
        version (str): PMS version. Default 1.10.1.4602
        startItem (:class:`~plexapi.media.Media`, optional): Media item in list/playlist/playqueue where playback should
                                                             start. Overrides existing startItem for playqueues if set.
        **kwargs: To allow overrides, this will be merged with the rest of the msg.

    Returns:
        dict: Returs a dict formatted correctly to start playback on a Chromecast.
    """

    if media is not None:
        # Lets set some params for the user if they use plexapi.
        server = media[0]._server if isinstance(media, list) else media._server
        server_url = urlparse(server._baseurl)
        protocol = server_url.scheme
        address = server_url.hostname
        port = server_url.port
        machineIdentifier = server.machineIdentifier
        token = server._token
        username = server.myPlexUsername
        myPlexSubscription = server.myPlexSubscription

        if getattr(media, "TYPE", None) == "playqueue":
            if startItem:
                media = media.items
            else:
                playQueue = media

        if playQueue is None:
            playQueue = server.createPlayQueue(media, startItem=startItem)

        playQueueID = playQueue.playQueueID
        contentId = playQueue.selectedItem.key
        contentType = playQueue.items[0].listType
        version = server.version

    # Chromecasts seem to start playback 5 seconds before the offset.
    if offset != 0:
        currentTime = offset

    msg = {
        "type": type,
        "requestId": requestId,
        "media": {
            "contentId": contentId,
            "streamType": streamType,
            "contentType": contentType,
            "customData": {
                "offset": offset,
                "directPlay": directPlay,
                "directStream": directStream,
                "subtitleSize": subtitleSize,
                "audioBoost": audioBoost,
                "server": {
                    "machineIdentifier": machineIdentifier,
                    "transcoderVideo": transcoderVideo,
                    "transcoderVideoRemuxOnly": transcoderVideoRemuxOnly,
                    "transcoderAudio": transcoderAudio,
                    "version": version,
                    "myPlexSubscription": myPlexSubscription,
                    "isVerifiedHostname": isVerifiedHostname,
                    "protocol": protocol,
                    "address": address,
                    "port": port,
                    "accessToken": token,
                    "user": {"username": username},
                },
                "containerKey": f"/playQueues/{playQueueID}?own=1&window=200",
            },
            "autoplay": autoplay,
            "currentTime": currentTime,
            "activeTrackIds": None,
        },
    }

    # Allow passing of kwargs to the dict.
    msg.update(kwargs)

    return msg


@property
def episode_title(self):
    """Return episode title."""
    return self.media_metadata.get("subtitle")


class PlexController(BaseController):
    # pylint: disable=too-many-public-methods
    """Controller to interact with Plex namespace."""

    def __init__(self):
        super().__init__("urn:x-cast:plex", "9AC194DC")
        self.app_id = "9AC194DC"
        self.namespace = "urn:x-cast:plex"
        self.request_id = 0
        self.play_media_event = threading.Event()
        self._last_play_msg = {}

    def _send_cmd(
        self,
        msg,
        namespace=None,
        inc_session_id=False,
        callback_function=None,
        inc=True,
    ):  # pylint: disable=too-many-arguments
        """Wrapper for the commands.

        Args:
            msg (dict): The actual command that will be sent.
            namespace (None, optional): What namespace should be used to send this.
            inc_session_id (bool, optional): Include session ID.
            callback_function (None, optional): If callback is provided it is
                                                executed after the command.
            inc (bool, optional): Increase the requestsId.
        """
        self.logger.debug(
            "Sending msg %r %s %s %s %s.",
            msg,
            namespace,
            inc_session_id,
            callback_function,
            inc,
        )

        if inc:
            self._inc_request()

        if namespace:
            old = self.namespace
            try:
                self.namespace = namespace
                self.send_message(
                    msg,
                    inc_session_id=inc_session_id,
                    callback_function=callback_function,
                )
            finally:
                self.namespace = old
        else:
            self.send_message(
                msg, inc_session_id=inc_session_id, callback_function=callback_function
            )

    def _inc_request(self):
        # Is this getting passed to Plex?
        self.request_id += 1
        return self.request_id

    def channel_connected(self):
        """Updates status when a media channel is connected."""
        self.update_status()

    def receive_message(self, _message, data: dict):
        """Called when a message from Plex to our controller is received.

        I haven't seen any message for it, but lets keep for for now.
        I have done minimal testing.

        Args:
            message (dict): Description
            data (dict): message.payload_utf8 interpreted as a JSON dict.

        Returns:
            bool: True if the message is handled.


        """
        if data[MESSAGE_TYPE] == TYPE_MEDIA_STATUS:
            self.logger.debug("(PlexController) MESSAGE RECEIVED: %r.", data)
            return True

        return False

    def update_status(self, callback_function_param=False):
        """Send message to update status."""
        self.send_message(
            {MESSAGE_TYPE: TYPE_GET_STATUS}, callback_function=callback_function_param
        )

    def stop(self):
        """Send stop command."""
        self._send_cmd({MESSAGE_TYPE: TYPE_STOP})

    def pause(self):
        """Send pause command."""
        self._send_cmd({MESSAGE_TYPE: TYPE_PAUSE})

    def play(self):
        """Send play command."""
        self._send_cmd({MESSAGE_TYPE: TYPE_PLAY})

    def previous(self):
        """Send previous command."""
        self._send_cmd({MESSAGE_TYPE: TYPE_PREVIOUS})

    def next(self):
        """Send next command."""
        self._send_cmd({MESSAGE_TYPE: TYPE_NEXT})

    def seek(self, position, resume_state="PLAYBACK_START"):
        """Send seek command.

        Args:
            position (int): Offset in seconds.
            resume_state (str, default): PLAYBACK_START
        """
        self._send_cmd(
            {MESSAGE_TYPE: TYPE_SEEK, SEEK_KEY: position, "resumeState": resume_state}
        )

    def rewind(self):
        """Rewind back to the start."""
        self.seek(0)

    def set_volume(self, percent):
        """Set the volume in percent (1-100).

        Args:
            percent (int): Percent of volume to be set.
        """
        self._socket_client.receiver_controller.set_volume(float(percent / 100))

    def volume_up(self, delta=0.1):
        """Increment volume by 0.1 (or delta) unless at max.
        Returns the new volume.
        """
        if delta <= 0:
            raise ValueError(f"volume delta must be greater than zero, not {delta}")
        return self.set_volume(self.status.volume_level + delta)

    def volume_down(self, delta=0.1):
        """Decrement the volume by 0.1 (or delta) unless at 0.
        Returns the new volume.
        """
        if delta <= 0:
            raise ValueError(f"volume delta must be greater than zero, not {delta}")
        return self.set_volume(self.status.volume_level - delta)

    def mute(self, status=None):
        """Toggle muting of audio.

        Args:
            status (None, optional): Override for on/off.
        """
        if status is None:
            status = not self.status.volume_muted

        self._socket_client.receiver_controller.set_volume_muted(status)

    def show_media(self, media=None, **kwargs):
        """Show media item's info on screen."""
        msg = media_to_chromecast_command(
            media, type=TYPE_DETAILS, requestId=self._inc_request(), **kwargs
        )

        def callback():  # pylint: disable=missing-docstring
            self._send_cmd(msg, inc_session_id=True, inc=False)

        self.launch(callback)

    def quit_app(self):
        """Quit the Plex app."""
        self._socket_client.receiver_controller.stop_app()

    @property
    def status(self):
        """Get the Chromecast's playing status.

        Returns:
            pychromecast.controllers.media.MediaStatus: Slightly modified status with patched
                                                        method for episode_title.
        """
        status = self._socket_client.media_controller.status
        status.episode_title = episode_title
        return status

    def _reset_playback(self, offset=None):
        """Reset playback.

        Args:
            offset (None, optional): Start playback from this offset in seconds,
                                     otherwise playback will start from current time.

        """
        if self._last_play_msg:
            offset_now = self.status.adjusted_current_time
            msg = deepcopy(self._last_play_msg)

            msg["media"]["customData"]["offset"] = (
                offset_now if offset is None else offset
            )
            msg["current_time"] = offset_now

            self._send_cmd(
                msg,
                namespace="urn:x-cast:com.google.cast.media",
                inc_session_id=True,
                inc=False,
            )
        else:
            self.logger.debug(
                "Can not reset the stream, _last_play_msg "
                "was not set with _send_start_play."
            )

    def _send_start_play(self, media=None, **kwargs):
        """Helper to send a playback command.

        Args:
            media (None, optional): :class:`~plexapi.base.Playable
            **kwargs: media_to_chromecast_command docs string.
        """
        msg = media_to_chromecast_command(
            media, requestiId=self._inc_request(), **kwargs
        )
        self.logger.debug("Create command: \n%r\n", json.dumps(msg, indent=4))
        self._last_play_msg = msg
        self._send_cmd(
            msg,
            namespace="urn:x-cast:com.google.cast.media",
            inc_session_id=True,
            inc=False,
        )

    def block_until_playing(self, media=None, timeout=None, **kwargs):
        """Block until media is playing, typically useful in a script.

        Another way to do the same is to check if the
        controller is_active or by using self.status.player_state.

        Args:
            media (None, optional): Can also be :class:`~plexapi.base.Playable
                                    if not, you need to fill out all the kwargs.
            timeout (None, int): default None
            **kwargs: See media_to_chromecast_command docs string.

        """
        # In case media isnt playing.
        self.play_media_event.clear()
        self.play_media(media, **kwargs)
        self.play_media_event.wait(timeout)
        self.play_media_event.clear()

    def play_media(self, media=None, **kwargs):
        """Start playback on the Chromecast.

        Args:
            media (None, optional): Can also be :class:`~plexapi.base.Playable
                                    if not, you need to fill out all the kwargs.
            **kwargs: See media_to_chromecast_command docs string.
        """
        self.play_media_event.clear()

        def app_launched_callback():  # pylint: disable=missing-docstring
            try:
                self._send_start_play(media, **kwargs)
            finally:
                self.play_media_event.set()

        self.launch(app_launched_callback)

    def join(self, timeout=None):
        """Join the thread."""
        self._socket_client.join(timeout=timeout)

    def disconnect(self, timeout=None, blocking=True):
        """Disconnect the controller."""
        self._socket_client.disconnect()
        if blocking:
            self.join(timeout=timeout)


# pylint: disable=too-many-public-methods
class PlexApiController(PlexController):
    """A controller that can use PlexAPI."""

    def __init__(self, pms):
        super().__init__()
        self.pms = pms

    def _get_current_media(self):
        """Get current media_item, media, & part for PMS."""
        key = int(self.status.content_id.split("/")[-1])
        media_item = self.pms.fetchItem(key).reload()
        media_idx = self.status.media_custom_data.get("mediaIndex", 0)
        part_idx = self.status.media_custom_data.get("partIndex", 0)
        media = media_item.media[media_idx]
        part = media.parts[part_idx]

        return media_item, media, part

    def _change_track(self, track, type_="subtitle", reset_playback=True):
        """Sets a new default audio/subtitle track.

        Args:
            track (None): The chosen track.
            type_ (str): The type of track.
            reset_playback (bool, optional): Reset playback after the track has
                                             been changed.

        Raises:
            ValueError: If type isn't subtitle or audio.
        """

        item, _, part = self._get_current_media()
        if type_ == "subtitle":
            method = part.subtitleStreams()
            default = part.setDefaultSubtitleStream
        elif type_ == "audio":
            method = part.audioStreams()
            default = part.setDefaultAudioStream
        else:
            raise ValueError("Set type parameter as subtitle or audio.")

        for track_ in method:
            if track in (track_.index, track_.language, track_.languageCode):
                self.logger.debug("Change %s to %s.", type_, track)
                default(track_)
                break

        item.reload()
        if reset_playback:
            self._reset_playback()

    def enable_audiotrack(self, audio):
        """Enable an audiotrack.

        Args:
            audio (str): Can be index, language or languageCode.
        """
        self._change_track(self, audio, "audio")

    def disable_subtitle(self):
        """Disable a subtitle track."""
        (
            _,
            __,
            part,
        ) = self._get_current_media()
        part.resetDefaultSubtitleStream()
        self._reset_playback()

    def enable_subtitle(self, subtitle):
        """Enable a subtitle track.

        Args:
            subtitle (str): Can be index, language or languageCode.
        """
        self._change_track(subtitle)

    def play_media(self, media=None, **kwargs):
        """Start playback on the Chromecast.

        Args:
            media (None, optional): Can also be :class:`~plexapi.base.Playable
                                    if not, you need to fill out all the kwargs.
            **kwargs: See media_to_chromecast_command docs string. `version` is set
                      to the version of the PMS reported by the API by default.
        """
        args = {"version": self.pms.version}
        args.update(kwargs)
        super().play_media(media, **args)
