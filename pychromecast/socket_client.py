"""
Module to interact with the ChromeCast via protobuf-over-socket.

Big thanks goes out to Fred Clift <fred@clift.org> who build the first
version of this code: https://github.com/minektur/chromecast-python-poc.
Without him this would not have been possible.
"""
import logging
import socket
import ssl
import json
import threading
import time
from collections import namedtuple
from struct import pack, unpack

from . import cast_channel_pb2
from .controllers import BaseController
from .controllers.media import MediaController
from .error import (
    ChromecastConnectionError,
    UnsupportedNamespace,
    NotConnected,
    PyChromecastStopped
)

NS_CONNECTION = 'urn:x-cast:com.google.cast.tp.connection'
NS_RECEIVER = 'urn:x-cast:com.google.cast.receiver'
NS_HEARTBEAT = 'urn:x-cast:com.google.cast.tp.heartbeat'

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

APP_ID = 'appId'
REQUEST_ID = "requestId"
SESSION_ID = "sessionId"


def _json_from_message(message):
    """ Parses a PB2 message into JSON format. """
    return json.loads(message.payload_utf8)


def _message_to_string(message, data=None):
    """ Gives a string representation of a PB2 message. """
    if data is None:
        data = _json_from_message(message)

    return "Message {} from {} to {}: {}".format(
        message.namespace, message.source_id, message.destination_id, data)

CastStatus = namedtuple('CastStatus',
                        ['is_active_input', 'is_stand_by', 'volume_level',
                         'volume_muted', 'app_id', 'display_name',
                         'namespaces', 'session_id', 'transport_id',
                         'status_text'])


# pylint: disable=too-many-instance-attributes
class SocketClient(threading.Thread):
    """ Class to interact with a Chromecast through a socket. """

    def __init__(self, host, tries=None):
        super(SocketClient, self).__init__()

        self.daemon = True

        self.logger = logging.getLogger(__name__)

        self.tries = tries
        self.host = host

        self.stop = threading.Event()

        self.receiver_controller = ReceiverController()
        self.media_controller = MediaController()

        # dict mapping namespace on Controller objects
        self._handlers = {}

        self.source_id = "sender-0"

        self.initialize_connection()

    def initialize_connection(self):
        tries = self.tries

        while tries is None or tries > 0:
            self.connecting = True

            self.app_namespaces = []
            self.destination_id = None
            self.session_id = None

            self._request_id = 0

            # dict mapping requestId on threading.Event objects
            self._request_callbacks = {}

            self._open_channels = []

            try:
                self.socket = ssl.wrap_socket(socket.socket())
                self.socket.settimeout(10)
                self.socket.connect((self.host, 8009))
                self.connecting = False
                self.logger.debug("Connected!")
                break
            except socket.error:
                self.connecting = True
                self.logger.exception("Failed to connect, retrying in 5s")
                time.sleep(5)
                if tries:
                    tries -= 1
        else:
            self.stop.set()
            self.logger.error("Failed to connect. No retries.")
            raise ChromecastConnectionError("Failed to connect")

        self.register_handler(HeartbeatController())
        self.register_handler(self.receiver_controller)
        self.register_handler(self.media_controller)

        self.receiver_controller.register_status_listener(self)

    def register_handler(self, handler):
        """ Register a new namespace handler. """
        self._handlers[handler.namespace] = handler

        handler.registered(self)

    def new_cast_status(self, cast_status):
        """ Called when a new cast status has been received. """
        new_channel = self.destination_id != cast_status.transport_id

        if new_channel:
            # Disconnect old channel
            self._disconnect_channel(self.destination_id)

        self.app_namespaces = cast_status.namespaces
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
        """ Start polling the socket. """
        self.receiver_controller.update_status()

        while not self.stop.is_set():
            try:
                message = self._read_message()
            except socket.error:
                if not self.connecting:
                    self.logger.exception("Connecting to chromecast...")
                    self.initialize_connection()
                continue

            data = _json_from_message(message)

            if message.namespace in self._handlers:

                if message.namespace != NS_HEARTBEAT:
                    self.logger.debug("Received: {}".format(
                        _message_to_string(message, data)))

                handled = self._handlers[message.namespace].receive_message(
                    message, data)

                if not handled:
                    self.logger.warning("Message unhandled: {}".format(
                        _message_to_string(message, data)))

            else:
                self.logger.error(
                    "Received unknown namespace: {}".format(
                        _message_to_string(message, data)))

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
        """ Reads a message from the socket and converts it to a message. """
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

        # pylint: disable=no-member
        message = cast_channel_pb2.CastMessage()
        message.ParseFromString(payload)

        return message

    # pylint: disable=too-many-arguments
    def send_message(self, destination_id, namespace, data,
                     inc_session_id=False, wait_for_response=False,
                     no_add_request_id=False):
        """ Send a message to the Chromecast. """

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

        # pylint: disable=no-member
        msg = cast_channel_pb2.CastMessage()

        msg.protocol_version = msg.CASTV2_1_0
        msg.source_id = self.source_id
        msg.destination_id = destination_id
        msg.payload_type = cast_channel_pb2.CastMessage.STRING
        msg.namespace = namespace
        msg.payload_utf8 = json.dumps(data, ensure_ascii=False).encode("utf8")

        #prepend message with Big-Endian 4 byte payload size
        be_size = pack(">I", msg.ByteSize())

        # Log all messages except heartbeat
        if msg.namespace != NS_HEARTBEAT:
            self.logger.debug(
                "Sending: {}".format(_message_to_string(msg, data)))

        if self.stop.is_set():
            raise PyChromecastStopped("Socket client's thread is stopped.")
        if not self.connecting:
            self.socket.sendall(be_size + msg.SerializeToString())
        else:
            raise NotConnected("Chromecast is connecting...")

        if not no_add_request_id and wait_for_response:
            self._request_callbacks[request_id] = threading.Event()
            self._request_callbacks[request_id].wait()

    def send_platform_message(self, namespace, message, inc_session_id=False,
                              wait_for_response=False):
        """ Helper method to send a message to the platform. """
        self.send_message(PLATFORM_DESTINATION_ID, namespace, message,
                          inc_session_id, wait_for_response)

    def send_app_message(self, namespace, message, inc_session_id=False,
                         wait_for_response=False):
        """ Helper method to send a message to current running app. """
        if namespace not in self.app_namespaces:
            raise UnsupportedNamespace(
                ("Namespace {} is not supported by current app. "
                 "Supported are {}").format(namespace,
                                            ", ".join(self.app_namespaces)))

        self.send_message(self.destination_id, namespace, message,
                          inc_session_id, wait_for_response)

    def _ensure_channel_connected(self, destination_id):
        """ Ensure we opened a channel to destination_id. """
        if destination_id not in self._open_channels:
            self._open_channels.append(destination_id)

            self.send_message(destination_id, NS_CONNECTION,
                              {MESSAGE_TYPE: TYPE_CONNECT,
                               'origin': {},
                               'userAgent': 'PyChromecast'},
                              no_add_request_id=True)

    def _disconnect_channel(self, destination_id):
        """ Disconnect a channel with destination_id. """
        if destination_id in self._open_channels:
            self.send_message(destination_id, NS_CONNECTION,
                              {MESSAGE_TYPE: TYPE_CLOSE, 'origin': {}},
                              no_add_request_id=True)

            self._open_channels.remove(destination_id)


class HeartbeatController(BaseController):
    """ Controller to respond to heartbeat messages. """

    def __init__(self):
        super(HeartbeatController, self).__init__(
            NS_HEARTBEAT, target_platform=True)

    def receive_message(self, message, data):
        """ Called when a heartbeat message is received. """
        if data[MESSAGE_TYPE] == TYPE_PING:
            self._socket_client.send_message(
                PLATFORM_DESTINATION_ID, self.namespace,
                {MESSAGE_TYPE: TYPE_PONG}, no_add_request_id=True)

            return True

        else:
            return False


class ReceiverController(BaseController):
    """ Controller to interact with the Chromecast platform. """

    def __init__(self):
        super(ReceiverController, self).__init__(
            NS_RECEIVER, target_platform=True)

        self.status = None

        self._status_listeners = []

    @property
    def app_id(self):
        """ Convenience method to retrieve current app id. """
        return self.status.app_id if self.status else None

    def receive_message(self, message, data):
        """ Called when a receiver-message has been received. """
        if data[MESSAGE_TYPE] == TYPE_RECEIVER_STATUS:
            self._process_get_status(data)

            return True

        else:
            return False

    def register_status_listener(self, listener):
        """ Register a status listener for when a new Chromecast status
            has been received. Listeners will be called with
            listener.new_channel(status) """
        self._status_listeners.append(listener)

    def update_status(self, blocking=False):
        """ Sends a message to the Chromecast to update the status. """
        self.send_message({MESSAGE_TYPE: TYPE_GET_STATUS},
                          wait_for_response=blocking)

    def launch_app(self, app_id, force_launch=False, block_till_launched=True):
        """ Launches an app on the Chromecast.

            Will only launch if it is not currently running unless
            force_launc=True. """
        if force_launch or self.app_id != app_id:
            self.send_message({MESSAGE_TYPE: TYPE_LAUNCH, APP_ID: app_id},
                              wait_for_response=block_till_launched)

    def stop_app(self):
        """ Stops the current running app on the Chromecast. """
        self.send_message({MESSAGE_TYPE: 'STOP'}, inc_session_id=True)

    def set_volume(self, volume):
        """ Allows to set volume. Should be value between 0..1.
        Returns the new volume.

        """
        volume = min(max(0, round(volume, 1)), 1)
        self.send_message({MESSAGE_TYPE: 'SET_VOLUME',
                           'volume': {'level': volume}})
        return volume

    def _process_get_status(self, data):
        """ Processes a received STATUS message and notifies listeners. """
        if not 'status' in data:
            return

        data = data['status']
        volume_data = data.get('volume', {})

        try:
            app_data = data['applications'][0]
        except KeyError:
            app_data = {}

        self.status = CastStatus(
            data.get('isActiveInput', False),
            data.get('isStandBy', True),
            volume_data.get('level', 1.0),
            volume_data.get('muted', False),
            app_data.get(APP_ID),
            app_data.get('displayName'),
            [item['name'] for item in app_data.get('namespaces', [])],
            app_data.get(SESSION_ID),
            app_data.get('transportId'),
            app_data.get('status_text', '')
            )

        self.logger.debug("Received: {}".format(self.status))

        for listener in self._status_listeners:
            try:
                listener.new_cast_status(self.status)
            except Exception:  # pylint: disable=broad-except
                pass

    def tear_down(self):
        """ Called when controller is destroyed. """
        super(ReceiverController, self).tear_down()

        self._status_listeners[:] = []
