"""
Provides a controller for controlling the default media players
on the Chromecast.
"""

from collections import namedtuple

from ..config import APP_MEDIA_RECEIVER
from . import BaseController

STREAM_TYPE_BUFFERED = "BUFFERED"

MEDIA_PLAYER_STATE_PLAYING = "PLAYING"
MEDIA_PLAYER_STATE_PAUSED = "PAUSED"
MEDIA_PLAYER_STATE_IDLE = "IDLE"

MediaStatus = namedtuple('MediaStatus',
                         ['current_time', 'content_id', 'content_type',
                          'duration', 'stream_type', 'idle_reason',
                          'media_session_id', 'playback_rate', 'player_state',
                          'supported_media_commands', 'volume_level',
                          'volume_muted', "media_customData"])

MESSAGE_TYPE = 'type'

TYPE_GET_STATUS = "GET_STATUS"
TYPE_MEDIA_STATUS = "MEDIA_STATUS"
TYPE_PLAY = "PLAY"
TYPE_PAUSE = "PAUSE"
TYPE_STOP = "STOP"
TYPE_LOAD = "LOAD"
TYPE_SEEK = "SEEK"


class MediaController(BaseController):
    """ Controller to interact with Google media namespace. """

    def __init__(self):
        super(MediaController, self).__init__(
            "urn:x-cast:com.google.cast.media")

        self.media_session_id = 0
        self.status = None

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
        if 'status' in data and len(data['status']) > 0:
            status_data = data['status'][0]
            media_data = status_data.get('media') or {}
            volume_data = status_data.get('volume', {})

            self.status = MediaStatus(
                status_data.get('currentTime', 0),
                media_data.get('contentId'),
                media_data.get('contentType'),
                media_data.get('duration', 0),
                media_data.get('streamType'),
                status_data.get('idleReason'),
                status_data.get('mediaSessionId'),
                status_data.get('playbackRate', 1),
                status_data.get('playerState'),
                status_data.get('supportedMediaCommands'),
                volume_data.get('level', 1.0),
                volume_data.get('muted', False),
                media_data.get('customData')
                )

        else:
            self.status = None

        self.logger.debug("Media:Received status {}".format(self.status))

        for listener in self._status_listeners:
            try:
                listener.new_media_status(self.status)
            except Exception:  # pylint: disable=broad-except
                pass

    # pylint: disable=too-many-arguments
    def play_media(self, url, content_type, title=None, thumb=None,
                   current_time=0, autoplay=True, stream_type=STREAM_TYPE_BUFFERED):
        """ Plays media on the Chromecast. Start default media receiver if not
            already started. """

        self._socket_client.receiver_controller.launch_app(APP_MEDIA_RECEIVER)

        msg = {
            'media': {
                'contentId': url,
                'streamType': stream_type,
                'contentType': content_type,
                #'metadata': {'type': 2,
                #             'metadataType': 0,
                #             'title': 'Main title PyChromecast!! :-)',
                #             'subtitle': "Subtitle"}
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
