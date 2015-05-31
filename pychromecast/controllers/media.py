"""
Provides a controller for controlling the default media players
on the Chromecast.
"""

from ..config import APP_MEDIA_RECEIVER
from . import BaseController

STREAM_TYPE_UNKNOWN = "UNKNOWN"
STREAM_TYPE_BUFFERED = "BUFFERED"

MEDIA_PLAYER_STATE_PLAYING = "PLAYING"
MEDIA_PLAYER_STATE_PAUSED = "PAUSED"
MEDIA_PLAYER_STATE_IDLE = "IDLE"
MEDIA_PLAYER_STATE_UNKNOWN = "UNKNOWN"

MESSAGE_TYPE = 'type'

TYPE_GET_STATUS = "GET_STATUS"
TYPE_MEDIA_STATUS = "MEDIA_STATUS"
TYPE_PLAY = "PLAY"
TYPE_PAUSE = "PAUSE"
TYPE_STOP = "STOP"
TYPE_LOAD = "LOAD"
TYPE_SEEK = "SEEK"


class MediaStatus(object):
    """ Class to hold the media status. """

    # pylint: disable=too-many-instance-attributes,too-few-public-methods
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

    def update(self, data):
        """ New data will only contain the changed attributes. """
        if len(data.get('status', [])) == 0:
            return

        status_data = data['status'][0]
        media_data = status_data.get('media') or {}
        volume_data = status_data.get('volume', {})

        self.current_time = status_data.get('currentTime', self.current_time),
        self.content_id = media_data.get('contentId', self.content_id)
        self.content_type = media_data.get('contentType', self.content_type)
        self.duration = media_data.get('duration', self.duration)
        self.stream_type = media_data.get('streamType', self.stream_type)
        self.idle_reason = status_data.get('idleReason', self.idle_reason)
        self.media_session_id = status_data.get(
            'mediaSessionId', self.media_session_id)
        self.playback_rate = status_data.get(
            'playbackRate', self.playback_rate)
        self.player_state = status_data.get('playerState', self.player_state)
        self.supported_media_commands = status_data.get(
            'supportedMediaCommands', self.supported_media_commands)
        self.volume_level = volume_data.get('level', self.volume_level)
        self.volume_muted = volume_data.get('muted', self.volume_muted)
        self.media_custom_data = media_data.get(
            'customData', self.media_custom_data)
        self.media_metadata = media_data.get('metadata', self.media_metadata)


class MediaController(BaseController):
    """ Controller to interact with Google media namespace. """

    def __init__(self):
        super(MediaController, self).__init__(
            "urn:x-cast:com.google.cast.media")

        self.media_session_id = 0
        self.status = MediaStatus()

        self._status_listeners = []

    def channel_connected(self):
        """ Called when media channel is connected. Will update status. """
        self.update_status()

    def receive_message(self, message, data):
        """ Called when a media message is received. """
        if data[MESSAGE_TYPE] == TYPE_MEDIA_STATUS:
            self._process_media_status(data)

            return True

        else:
            return False

    def register_status_listener(self, listener):
        """ Register a listener for new media statusses. A new status will
            call listener.new_media_status(status) """
        self._status_listeners.append(listener)

    def update_status(self, blocking=False):
        """ Send message to update the status. """
        self.send_message({MESSAGE_TYPE: TYPE_GET_STATUS},
                          wait_for_response=blocking)

    def _send_command(self, command):
        """ Send a command to the Chromecast on media channel. """
        if self.status is None or self.status.media_session_id is None:
            return

        command['mediaSessionId'] = self.status.media_session_id

        self.send_message(command, inc_session_id=True)

    @property
    def is_playing(self):
        """ Returns if the Chromecast is playing. """
        return (self.status is not None and
                self.status.player_state == MEDIA_PLAYER_STATE_PLAYING)

    @property
    def is_paused(self):
        """ Returns if the Chromecast is paused. """
        return (self.status is not None and
                self.status.player_state == MEDIA_PLAYER_STATE_PAUSED)

    @property
    def is_idle(self):
        """ Returns if the Chromecast is idle on a media supported app. """
        return (self.status is not None and
                self.status.player_state == MEDIA_PLAYER_STATE_IDLE)

    @property
    def title(self):
        """ Return title of the current playing item. """
        if not self.status:
            return None

        return self.status.media_metadata.get('title')

    @property
    def thumbnail(self):
        """ Return thumbnail url of current playing item. """
        if not self.status:
            return None

        images = self.status.media_metadata.get('images')

        return images[0]['url'] if images and len(images) > 0 else None

    def play(self):
        """ Send the PLAY command. """
        self._send_command({MESSAGE_TYPE: TYPE_PLAY})

    def pause(self):
        """ Send the PAUSE command. """
        self._send_command({MESSAGE_TYPE: TYPE_PAUSE})

    def stop(self):
        """ Send the STOP command. """
        self._send_command({MESSAGE_TYPE: TYPE_STOP})

    def rewind(self):
        """ Starts playing the media from the beginning. """
        self.seek(0)

    def seek(self, position):
        """ Seek the media to a specific location. """
        self._send_command({MESSAGE_TYPE: TYPE_SEEK,
                            "currentTime": position,
                            "resumeState": "PLAYBACK_START"})

    def _process_media_status(self, data):
        """ Processes a STATUS message. """
        self.status.update(data)

        self.logger.debug("Media:Received status %s", data)

        for listener in self._status_listeners:
            try:
                listener.new_media_status(self.status)
            except Exception:  # pylint: disable=broad-except
                pass

    # pylint: disable=too-many-arguments
    def play_media(self, url, content_type, title=None, thumb=None,
                   current_time=0, autoplay=True,
                   stream_type=STREAM_TYPE_BUFFERED):
        """ Plays media on the Chromecast. Start default media receiver if not
            already started. """

        self._socket_client.receiver_controller.launch_app(APP_MEDIA_RECEIVER)

        msg = {
            'media': {
                'contentId': url,
                'streamType': stream_type,
                'contentType': content_type,
                # 'metadata': {'type': 2,
                #              'metadataType': 0,
                #              'title': 'Main title PyChromecast!! :-)',
                #              'subtitle': "Subtitle"}
            },
            MESSAGE_TYPE: TYPE_LOAD,
            'currentTime': current_time,
            'autoplay': autoplay,
            'customData': {}
        }

        if title:
            msg['customData']['payload']['title'] = title

        if thumb:
            msg['customData']['payload']['thumb'] = thumb

        self.send_message(msg, inc_session_id=True)

    def tear_down(self):
        """ Called when controller is destroyed. """
        super(MediaController, self).tear_down()

        self._status_listeners[:] = []
