import logging
import socket
import ssl
import time
from struct import pack, unpack
import json
import threading
from collections import namedtuple

import cast_channel_pb2
from config import APP_ID

NAMESPACE = {
    'connection': 'urn:x-cast:com.google.cast.tp.connection',
    'receiver': 'urn:x-cast:com.google.cast.receiver',
    'cast': 'urn:x-cast:com.google.cast.media',
    'heartbeat': 'urn:x-cast:com.google.cast.tp.heartbeat',
    'message': 'urn:x-cast:com.google.cast.player.message',
    'media': "urn:x-cast:com.google.cast.media",
}

PLATFORM_DESTINATION_ID = "receiver-0"

MESSAGE_TYPE = 'type'
TYPE_PING = "PING"
TYPE_RECEIVER_STATUS = "RECEIVER_STATUS"
TYPE_PONG = "PONG"
TYPE_CONNECT = "CONNECT"
TYPE_CLOSE = "CLOSE"
TYPE_GET_STATUS = "GET_STATUS"
TYPE_LAUNCH = "LAUNCH"
TYPE_LOAD = "LOAD"
TYPE_MEDIA_STATUS = "MEDIA_STATUS"

REQUEST_ID = "requestId"
SESSION_ID = "sessionId"

STREAM_TYPE_BUFFERED = "BUFFERED"


def json_from_message(message):
    return json.loads(message.payload_utf8)


def message_to_string(message, data=None):
    if data is None:
        data = json_from_message(message)

    return "Message {} from {} to {}: {}".format(
        message.namespace, message.source_id, message.destination_id, data)

CastStatus = namedtuple('CastStatus',
                        ['is_active_input', 'is_stand_by', 'volume_level',
                         'volume_muted', 'app_id', 'display_name',
                         'namespaces', 'session_id', 'transport_id',
                         'status_text'])

MediaStatus = namedtuple('MediaStatus',
                         ['current_time', 'content_id', 'content_type',
                          'duration', 'stream_type', 'media_session_id',
                          'playback_rate', 'player_state',
                          'supported_media_commands', 'volume_level',
                          'volume_muted'])


class SocketClient(threading.Thread):

    def __init__(self, host):
        super(SocketClient, self).__init__()

        self.logger = logging.getLogger(__name__)

        self.host = host
        self.stop = threading.Event()

        self.source_id = "sender-0"
        self.app_id = None
        self.destination_id = None
        self.session_id = None

        self._request_id = 0

        # dict mapping namespace on Controller objects
        self._handlers = {}

        # dict mapping requestId on threading.Event objects
        self._request_callbacks = {}

        self._open_channels = []

        # Initialize the socket
        self.socket = ssl.wrap_socket(socket.socket())

        try:
            # TODO add timeout
            self.socket.connect((self.host, 8009))
        except socket.error:
            # TODO
            pass

        # Setup handlers
        HeartbeatController(self)
        self.receiver_controller = ReceiverController(self)
        self.media_controller = MediaController(self)

        self.receiver_controller.register_status_listener(self)

        self.receiver_controller.update_status()

        # Start listening
        self.start()

    @property
    def is_connected(self):
        return self.socket is not None

    def register_handler(self, namespace, handler):
        self._handlers[namespace] = handler

    def on_new_status(self, cast_status):
        new_channel = self.destination_id != cast_status.transport_id

        if new_channel:
            # Disconnect old channel
            self._disconnect_channel(self.destination_id)

        self.app_id = cast_status.app_id
        self.destination_id = cast_status.transport_id
        self.session_id = cast_status.session_id

        if new_channel:
            # If any of the namespaces of the new app are supported
            # we will automatically connect to it to receive updates
            match_ns = [value for key, value in self._handlers.items()
                        if key in cast_status.namespaces]

            if match_ns:
                self._ensure_channel_connected(self.destination_id)

                for handler in match_ns:
                    handler.channel_connected()

    def _gen_request_id(self):
        """ Generates a unique request id. """
        self._request_id += 1

        return self._request_id

    def run(self):
        while not self.stop.is_set():
            message = self._read_message()

            data = json_from_message(message)

            if message.namespace in self._handlers:

                if message.namespace != NAMESPACE['heartbeat']:
                    self.logger.debug("Received: {}".format(
                        message_to_string(message, data)))

                self._handlers[message.namespace].receive_message(
                    message, data)

            else:
                self.logger.error(
                    "Received unknown namespace: {}".format(
                        message_to_string(message, data)))

            if REQUEST_ID in data:
                event = self._request_callbacks.pop(data[REQUEST_ID], None)

                if event is not None:
                    event.set()

        for handler in self._handlers.values():
            handler.tear_down()

        for channel in self._open_channels:
            self._disconnect_channel(channel)

        self.socket.close()

    def _read_message(self):
        # first 4 bytes is Big-Endian payload length
        payload_info = ""

        while len(payload_info) < 4:
            frag = self.socket.recv(1)
            payload_info += frag

        read_len = unpack(">I", payload_info)[0]

        #now read the payload
        payload = ""
        while len(payload) < read_len:
            frag = self.socket.recv(2048)
            payload += frag

        message = cast_channel_pb2.CastMessage()
        message.ParseFromString(payload)

        return message

    def send_message(self, destination_id, namespace, data,
                     inc_session_id=False, wait_for_response=False,
                     no_add_request_id=False):
        # namespace is a string containing namespace
        # data is a dict that will be converted to json
        # wait_for_response only works if we have a request id

        # If channel is not open yet, connect to it.
        self._ensure_channel_connected(destination_id)

        if not no_add_request_id:
            request_id = self._gen_request_id()
            data[REQUEST_ID] = request_id

        if inc_session_id:
            data[SESSION_ID] = self.session_id

        msg = cast_channel_pb2.CastMessage()

        msg.protocol_version = msg.CASTV2_1_0
        msg.source_id = self.source_id
        msg.destination_id = destination_id
        msg.payload_type = cast_channel_pb2.CastMessage.STRING
        msg.namespace = namespace
        msg.payload_utf8 = json.dumps(data, ensure_ascii=False).encode("utf8")

        #prepend message with Big-Endian 4 byte payload size
        be_size = pack(">I", msg.ByteSize())

        if msg.namespace != NAMESPACE['heartbeat']:
            self.logger.debug(
                "Sending: {}".format(message_to_string(msg, data)))

        self.socket.sendall(be_size + msg.SerializeToString())

        if not no_add_request_id and wait_for_response:
            self._request_callbacks[request_id] = threading.Event()
            self._request_callbacks[request_id].wait()

    def send_platform_message(self, namespace, message, inc_session_id=False,
                              wait_for_response=False):
        self.send_message(PLATFORM_DESTINATION_ID, namespace, message,
                          inc_session_id, wait_for_response)

    def send_app_message(self, namespace, message, inc_session_id=False,
                         wait_for_response=False):
        self.send_message(self.destination_id, namespace, message,
                          inc_session_id, wait_for_response)

    def _ensure_channel_connected(self, destination_id):
        if destination_id not in self._open_channels:
            self._open_channels.append(destination_id)

            self.send_message(destination_id, NAMESPACE['connection'],
                              {MESSAGE_TYPE: TYPE_CONNECT, 'origin': {}},
                              no_add_request_id=True)

    def _disconnect_channel(self, destination_id):
        if destination_id in self._open_channels:
            self.send_message(destination_id, NAMESPACE['connection'],
                              {MESSAGE_TYPE: TYPE_CLOSE, 'origin': {}},
                              no_add_request_id=True)

            self._open_channels.remove(destination_id)


class BaseController(object):
    def __init__(self, namespace, socket_client, target_platform=False):
        self.namespace = namespace
        self._socket_client = socket_client
        self.target_platform = target_platform

        self.logger = logging.getLogger(__name__)

        socket_client.register_handler(namespace, self)

    def channel_connected(self):
        pass

    def send_message(self, data, inc_session_id=False,
                     wait_for_response=False):
        if self.target_platform:
            self._socket_client.send_platform_message(
                self.namespace, data, inc_session_id, wait_for_response)

        else:
            self._socket_client.send_app_message(
                self.namespace, data, inc_session_id, wait_for_response)

    def receive_message(self, message, data):
        self.logger.debug("Message unhandled: {}".format(
            message_to_string(message, data)))

    def tear_down(self):
        self._socket_client = None


class HeartbeatController(BaseController):
    def __init__(self, socket_client):
        super(HeartbeatController, self).__init__(
            NAMESPACE['heartbeat'], socket_client, target_platform=True)

    def receive_message(self, message, data):
        if data[MESSAGE_TYPE] == TYPE_PING:
            self._socket_client.send_message(
                PLATFORM_DESTINATION_ID, self.namespace,
                {MESSAGE_TYPE: TYPE_PONG}, no_add_request_id=True)

        else:
            super(HeartbeatController, self).receive_message(message, data)


class ReceiverController(BaseController):
    def __init__(self, socket_client):
        super(ReceiverController, self).__init__(
            NAMESPACE['receiver'], socket_client, target_platform=True)

        self._status_listeners = []

    def receive_message(self, message, data):
        if data[MESSAGE_TYPE] == TYPE_RECEIVER_STATUS:
            self._process_get_status(data)

        else:
            super(ReceiverController, self).receive_message(message, data)

    def register_status_listener(self, listener):
        self._status_listeners.append(listener)

    def update_status(self):
        self.send_message({MESSAGE_TYPE: TYPE_GET_STATUS})

    def launch_app(self, app_id, block_till_launched=True):
        self.send_message({MESSAGE_TYPE: TYPE_LAUNCH, 'appId': app_id},
                          wait_for_response=block_till_launched)

    def stop_app(self):
        self.send_message({MESSAGE_TYPE: 'STOP'}, inc_session_id=True)

    def _process_get_status(self, data):
        if not 'status' in data:
            return

        data = data['status']
        volume_data = data.get('volume', {})

        try:
            app_data = data['applications'][0]
        except KeyError:
            app_data = {}

        status = CastStatus(
            data.get('isActiveInput', False),
            data.get('isStandBy', True),
            volume_data.get('level', 1.0),
            volume_data.get('muted', False),
            app_data.get('appId'),
            app_data.get('displayName'),
            [item['name'] for item in app_data.get('namespaces', [])],
            app_data.get('sessionId'),
            app_data.get('transportId'),
            app_data.get('status_text', '')
            )

        self.logger.debug("Received: {}".format(status))

        for listener in self._status_listeners:
            listener.on_new_status(status)

    def tear_down(self):
        super(ReceiverController, self).tear_down()

        self._status_listeners[:] = []


class MediaController(BaseController):
    def __init__(self, socket_client):
        super(MediaController, self).__init__(
            NAMESPACE['media'], socket_client)

        self.media_session_id = 0
        self.status = None

    def channel_connected(self):
        self.update_status()

    def receive_message(self, message, data):
        if data[MESSAGE_TYPE] == TYPE_MEDIA_STATUS:
            self._process_media_status(data)

        else:
            super(MediaController, self).receive_message(message, data)

    def update_status(self):
        self.send_message({MESSAGE_TYPE: TYPE_GET_STATUS})

    def _send_command(self, command):
        if self.status is None or self.status.media_session_id is None:
            return

        command['mediaSessionId'] = self.status.media_session_id

        self.send_message(command)

    def play(self):
        self._send_command({MESSAGE_TYPE: 'PLAY'})

    def pause(self):
        self._send_command({MESSAGE_TYPE: 'PAUSE'})

        """
{'requestId': 3,
 'status': [{'currentTime': 122.836466,
             'mediaSessionId': 9,
             'playbackRate': 1,
             'playerState': 'PAUSED',
             'supportedMediaCommands': 15,
             'volume': {'level': 1, 'muted': False}}],
 'type': 'MEDIA_STATUS'}
        """

    def stop(self):
        self._send_command({MESSAGE_TYPE: 'STOP'})

        """
{'requestId': 3,
 'status': [{'currentTime': 0,
             'idleReason': 'CANCELLED',
             'mediaSessionId': 8,
             'playbackRate': 1,
             'playerState': 'IDLE',
             'supportedMediaCommands': 15,
             'volume': {'level': 1, 'muted': False}}],
 'type': 'MEDIA_STATUS'}
        """

    def _process_media_status(self, data):
        if 'status' in data:
            status_data = data.get('status', [{}])[0]
            media_data = status_data.get('media', {})
            volume_data = status_data.get('volume', {})

            self.status = MediaStatus(
                status_data.get('currentTime', 0),
                media_data.get('contentId'),
                media_data.get('contentType'),
                media_data.get('duration', 0),
                media_data.get('streamType'),
                status_data.get('mediaSessionId'),
                status_data.get('playbackRate', 1),
                status_data.get('playerState'),
                status_data.get('supportedMediaCommands'),
                volume_data.get('level', 1.0),
                volume_data.get('muted', False)
                )

        else:
            self.status = None

        self.logger.debug("Media:Received status {}".format(self.status))

    def play_media(self, url, stream_type, content_type, title=None,
                   thumb=None, current_time=0, autoplay=True):

        if self._socket_client.app_id != APP_ID['DEFAULT_MEDIA_RECEIVER']:
            self._socket_client.receiver_controller.launch_app(
                APP_ID['DEFAULT_MEDIA_RECEIVER'])

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
            #'customData': {}
        }

        #if title:
        #    msg['customData']['payload']['title'] = title

        #if thumb:
        #    msg['customData']['payload']['thumb'] = thumb

        self.send_message(msg, inc_session_id=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    client = SocketClient("192.168.1.9")

    i = 0

    try:
        while True:
            i += 1
            if i == 5:
                #client.media_controller.update_status()
                #client.media_controller.seek(10)
                pass
                #client.receiver_controller.launch_app("CC1AD845")
                #client.media_controller.play_media(
                #    "http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4",
                #    STREAM_TYPE_BUFFERED, "video/mp4")


            time.sleep(1)
    except KeyboardInterrupt:
        client.stop.set()

    time.sleep(1)
