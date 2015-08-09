"""
Module to interact with the ChromeCast via protobuf-over-socket.

Big thanks goes out to Fred Clift <fred@clift.org> who build the first
version of this code: https://github.com/minektur/chromecast-python-poc.
Without him this would not have been possible.
"""
# Pylint does not understand the protobuf objects correctly
# pylint: disable=no-member

import logging
import socket
import ssl
import json
import threading
import time
from collections import namedtuple
from struct import pack, unpack

from . import cast_channel_pb2
import sys
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


if sys.version_info >= (3, 0):
    def _json_to_payload(data):
        """ Encodes a python value into JSON format. """
        return json.dumps(data, ensure_ascii=False).encode("utf8")
else:
    def _json_to_payload(data):
        """ Encodes a python value into JSON format. """
        return json.dumps(data, ensure_ascii=False)


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

        self.source_id = "sender-0"
        self.stop = threading.Event()

        self.app_namespaces = []
        self.destination_id = None
        self.session_id = None
        self._request_id = 0
        # dict mapping requestId on threading.Event objects
        self._request_callbacks = {}
        self._open_channels = []

        self.connecting = True
        self.socket = None

        # dict mapping namespace on Controller objects
        self._handlers = {}

        self.receiver_controller = ReceiverController()
        self.media_controller = MediaController()

        self.register_handler(HeartbeatController())
        self.register_handler(ConnectionController())
        self.register_handler(self.receiver_controller)
        self.register_handler(self.media_controller)

        self.receiver_controller.register_status_listener(self)

        self.initialize_connection()

    def initialize_connection(self):
        """Initialize a socket to a Chromecast, retrying as necessary."""
        tries = self.tries

        if self.socket is not None:
            self.socket.close()
            self.socket = None

        # Make sure nobody is blocking.
        for event in self._request_callbacks.values():
            event.set()

        self.app_namespaces = []
        self.destination_id = None
        self.session_id = None
        self._request_id = 0
        self._request_callbacks = {}
        self._open_channels = []

        self.connecting = True

        while tries is None or tries > 0:
            try:
                self.socket = ssl.wrap_socket(socket.socket())
                self.socket.settimeout(60)
                self.socket.connect((self.host, 8009))
                self.connecting = False
                self.receiver_controller.update_status()

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

    def register_handler(self, handler):
        """ Register a new namespace handler. """
        self._handlers[handler.namespace] = handler

        handler.registered(self)

    def new_cast_status(self, cast_status):
        """ Called when a new cast status has been received. """
        new_channel = self.destination_id != cast_status.transport_id

        if new_channel:
            self._disconnect_channel(self.destination_id)

        self.app_namespaces = cast_status.namespaces
        self.destination_id = cast_status.transport_id
        self.session_id = cast_status.session_id

        if new_channel:
            # If any of the namespaces of the new app are supported
            # we will automatically connect to it to receive updates
            for namespace in self.app_namespaces:
                if namespace in self._handlers:
                    self._ensure_channel_connected(self.destination_id)
                    self._handlers[namespace].channel_connected()

    def _gen_request_id(self):
        """ Generates a unique request id. """
        self._request_id += 1

        return self._request_id

    @property
    def is_stopped(self):
        """ Returns boolean if the connection has been stopped. """
        return self.stop.is_set()

    def run(self):
        """ Start polling the socket. """
        # pylint: disable=too-many-branches
        while not self.stop.is_set():
            try:
                message = self._read_message()
            except socket.error:
                self.logger.exception(
                    "Error communicating with socket, resetting connection")
                self.initialize_connection()
                continue

            data = _json_from_message(message)

            if message.namespace in self._handlers:

                if message.namespace != NS_HEARTBEAT:
                    self.logger.debug(
                        "Received: %s", _message_to_string(message, data))

                try:
                    handled = \
                        self._handlers[message.namespace].receive_message(
                            message, data)

                    if not handled:
                        self.logger.warning(
                            "Message unhandled: %s",
                            _message_to_string(message, data))
                except Exception:  # pylint: disable=broad-except
                    self.logger.exception(
                        (u"Exception caught while sending message to "
                         u"controller %s: %s"),
                        type(self._handlers[message.namespace]).__name__,
                        _message_to_string(message, data))

            else:
                self.logger.warning(
                    "Received unknown namespace: %s",
                    _message_to_string(message, data))

            if REQUEST_ID in data:
                event = self._request_callbacks.pop(data[REQUEST_ID], None)

                if event is not None:
                    event.set()

        # Clean up
        for channel in self._open_channels:
            try:
                self._disconnect_channel(channel)
            except Exception:  # pylint: disable=broad-except
                pass

        for handler in self._handlers.values():
            try:
                handler.tear_down()
            except Exception:  # pylint: disable=broad-except
                pass

        self.socket.close()

    def _read_bytes_from_socket(self, msglen):
        """ Read bytes from the socket. """
        chunks = []
        bytes_recd = 0
        while bytes_recd < msglen:
            chunk = self.socket.recv(min(msglen - bytes_recd, 2048))
            if chunk == b'':
                raise RuntimeError("socket connection broken")
            chunks.append(chunk)
            bytes_recd += len(chunk)
        return b''.join(chunks)

    def _read_message(self):
        """ Reads a message from the socket and converts it to a message. """
        # first 4 bytes is Big-Endian payload length
        payload_info = self._read_bytes_from_socket(4)
        read_len = unpack(">I", payload_info)[0]

        # now read the payload
        payload = self._read_bytes_from_socket(read_len)

        # pylint: disable=no-member
        message = cast_channel_pb2.CastMessage()
        message.ParseFromString(payload)

        return message

    # pylint: disable=too-many-arguments
    def send_message(self, destination_id, namespace, data,
                     inc_session_id=False, wait_for_response=False,
                     no_add_request_id=False, force=False):
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
        msg.payload_utf8 = _json_to_payload(data)

        # prepend message with Big-Endian 4 byte payload size
        be_size = pack(">I", msg.ByteSize())

        # Log all messages except heartbeat
        if msg.namespace != NS_HEARTBEAT:
            self.logger.debug("Sending: %s", _message_to_string(msg, data))

        if not force and self.stop.is_set():
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

            self.send_message(
                destination_id, NS_CONNECTION,
                {MESSAGE_TYPE: TYPE_CONNECT,
                 'origin': {},
                 'userAgent': 'PyChromecast',
                 'senderInfo': {
                     'sdkType': 2,
                     'version': '15.605.1.3',
                     'browserVersion': "44.0.2403.30",
                     'platform': 4,
                     'systemVersion': 'Macintosh; Intel Mac OS X10_10_3',
                     'connectionType': 1}},
                no_add_request_id=True)

    def _disconnect_channel(self, destination_id):
        """ Disconnect a channel with destination_id. """
        if destination_id in self._open_channels:
            self.send_message(
                destination_id, NS_CONNECTION,
                {MESSAGE_TYPE: TYPE_CLOSE, 'origin': {}},
                no_add_request_id=True, force=True)

            self._open_channels.remove(destination_id)

            self.handle_channel_disconnected()

    def handle_channel_disconnected(self):
        """ Handles a channel being disconnected. """
        for namespace in self.app_namespaces:
            if namespace in self._handlers:
                self._handlers[namespace].channel_disconnected()

        self.app_namespaces = []
        self.destination_id = None
        self.session_id = None


class ConnectionController(BaseController):
    """ Controller to respond to connection messages. """

    def __init__(self):
        super(ConnectionController, self).__init__(NS_CONNECTION)

    def receive_message(self, message, data):
        """ Called when a connection message is received. """
        if self._socket_client.is_stopped:
            return True

        if data[MESSAGE_TYPE] == TYPE_CLOSE:
            self._socket_client.handle_channel_disconnected()

            return True

        else:
            return False


class HeartbeatController(BaseController):
    """ Controller to respond to heartbeat messages. """

    def __init__(self):
        super(HeartbeatController, self).__init__(
            NS_HEARTBEAT, target_platform=True)

    def receive_message(self, message, data):
        """ Called when a heartbeat message is received. """
        if self._socket_client.is_stopped:
            return True

        if data[MESSAGE_TYPE] == TYPE_PING:
            try:
                self._socket_client.send_message(
                    PLATFORM_DESTINATION_ID, self.namespace,
                    {MESSAGE_TYPE: TYPE_PONG}, no_add_request_id=True)
            except PyChromecastStopped:
                self._socket_client.logger.exception(
                    "Heartbeat error when sending response, "
                    "Chromecast connection has stopped")

            return True

        else:
            return False

    def ping(self):
        """ Send a ping message. """
        self.send_message({MESSAGE_TYPE: TYPE_PING})


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
            listener.new_cast_status(status) """
        self._status_listeners.append(listener)

    def update_status(self, blocking=False):
        """ Sends a message to the Chromecast to update the status. """
        self.logger.info("Receiver:Updating status")
        self.send_message({MESSAGE_TYPE: TYPE_GET_STATUS},
                          wait_for_response=blocking)

    def launch_app(self, app_id, force_launch=False, block_till_launched=True):
        """ Launches an app on the Chromecast.

            Will only launch if it is not currently running unless
            force_launc=True. """
        # If this is called too quickly after launch, we don't have the info.
        # We need the info if we are not force launching to check running app.
        if not force_launch and self.app_id is None:
            self.update_status(True)

        if force_launch or self.app_id != app_id:
            self.logger.info("Receiver:Launching app %s", app_id)
            self.send_message({MESSAGE_TYPE: TYPE_LAUNCH, APP_ID: app_id},
                              wait_for_response=block_till_launched)
        else:
            self.logger.info(
                "Not launching app %s - already running", app_id)

    def stop_app(self):
        """ Stops the current running app on the Chromecast. """
        self.logger.info("Receiver:Stopping current app")
        self.send_message(
            {MESSAGE_TYPE: 'STOP'},
            inc_session_id=True, wait_for_response=True)

    def set_volume(self, volume):
        """ Allows to set volume. Should be value between 0..1.
        Returns the new volume.

        """
        volume = min(max(0, volume), 1)
        self.logger.info("Receiver:setting volume to %.1f", volume)
        self.send_message({MESSAGE_TYPE: 'SET_VOLUME',
                           'volume': {'level': volume}})
        return volume

    def set_volume_muted(self, muted):
        """ Allows to mute volume. """
        self.send_message(
            {MESSAGE_TYPE: 'SET_VOLUME',
             'volume': {'muted': muted}})

    def _process_get_status(self, data):
        """ Processes a received STATUS message and notifies listeners. """
        data = data.get('status', {})

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

        self.logger.debug("Received: %s", self.status)

        for listener in self._status_listeners:
            try:
                listener.new_cast_status(self.status)
            except Exception:  # pylint: disable=broad-except
                pass

    def tear_down(self):
        """ Called when controller is destroyed. """
        super(ReceiverController, self).tear_down()

        self._status_listeners[:] = []
