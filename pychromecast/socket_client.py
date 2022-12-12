"""
Module to interact with the ChromeCast via protobuf-over-socket.

Big thanks goes out to Fred Clift <fred@clift.org> who build the first
version of this code: https://github.com/minektur/chromecast-python-poc.
Without him this would not have been possible.
"""
# pylint: disable=too-many-lines

import abc
import errno
import json
import logging
import select
import socket
import ssl
import sys
import threading
import time
from collections import defaultdict, namedtuple
from struct import pack, unpack

from . import cast_channel_pb2
from .controllers import BaseController
from .controllers.media import MediaController
from .controllers.receiver import ReceiverController
from .const import MESSAGE_TYPE, REQUEST_ID, SESSION_ID
from .dial import get_host_from_service
from .error import (
    ChromecastConnectionError,
    UnsupportedNamespace,
    NotConnected,
    PyChromecastStopped,
)

NS_CONNECTION = "urn:x-cast:com.google.cast.tp.connection"
NS_HEARTBEAT = "urn:x-cast:com.google.cast.tp.heartbeat"

PLATFORM_DESTINATION_ID = "receiver-0"

TYPE_PING = "PING"
TYPE_PONG = "PONG"
TYPE_CONNECT = "CONNECT"
TYPE_CLOSE = "CLOSE"
TYPE_LOAD = "LOAD"

# The socket connection is being setup
CONNECTION_STATUS_CONNECTING = "CONNECTING"
# The socket connection was complete
CONNECTION_STATUS_CONNECTED = "CONNECTED"
# The socket connection has been disconnected
CONNECTION_STATUS_DISCONNECTED = "DISCONNECTED"
# Connecting to socket failed (after a CONNECTION_STATUS_CONNECTING)
CONNECTION_STATUS_FAILED = "FAILED"
# Failed to resolve service name
CONNECTION_STATUS_FAILED_RESOLVE = "FAILED_RESOLVE"
# The socket connection was lost and needs to be retried
CONNECTION_STATUS_LOST = "LOST"

HB_PING_TIME = 10
HB_PONG_TIME = 10
POLL_TIME_BLOCKING = 5.0
POLL_TIME_NON_BLOCKING = 0.01
TIMEOUT_TIME = 30
RETRY_TIME = 5


class InterruptLoop(Exception):
    """The chromecast has been manually stopped."""


def _dict_from_message_payload(message):
    """Parses a PB2 message as a JSON dict."""
    try:
        data = json.loads(message.payload_utf8)
        if not isinstance(data, dict):
            logger = logging.getLogger(__name__)
            logger.debug(
                "Non dict json in namespace %s: '%s'",
                message.namespace,
                message.payload_utf8,
            )
            return {}
        return data
    except ValueError:
        logger = logging.getLogger(__name__)
        logger.debug(
            "Invalid json in namespace %s: '%s'",
            message.namespace,
            message.payload_utf8,
        )
        return {}


def _message_to_string(message, data=None):
    """Gives a string representation of a PB2 message."""
    if data is None:
        data = _dict_from_message_payload(message)

    return (
        f"Message {message.namespace} from {message.source_id} to "
        f"{message.destination_id}: {data or message.payload_utf8}"
    )


if sys.version_info >= (3, 0):

    def _json_to_payload(data):
        """Encodes a python value into JSON format."""
        return json.dumps(data, ensure_ascii=False).encode("utf8")

else:

    def _json_to_payload(data):
        """Encodes a python value into JSON format."""
        return json.dumps(data, ensure_ascii=False)


def _is_ssl_timeout(exc):
    """Returns True if the exception is for an SSL timeout"""
    return exc.message in (
        "The handshake operation timed out",
        "The write operation timed out",
        "The read operation timed out",
    )


NetworkAddress = namedtuple("NetworkAddress", ["address", "port"])

ConnectionStatus = namedtuple("ConnectionStatus", ["status", "address"])


class ConnectionStatusListener(abc.ABC):
    """Listener for receiving connection status events."""

    @abc.abstractmethod
    def new_connection_status(self, status: ConnectionStatus):
        """Updated connection status."""


# pylint: disable-next=too-many-instance-attributes
class SocketClient(threading.Thread):
    """
    Class to interact with a Chromecast through a socket.

    :param host: The host to connect to.
    :param port: The port to use when connecting to the device, set to None to
                 use the default of 8009. Special devices such as Cast Groups
                 may return a different port number so we need to use that.
    :param cast_type: The type of chromecast to connect to, see
                      dial.CAST_TYPE_* for types.
    :param tries: Number of retries to perform if the connection fails.
                  None for infinite retries.
    :param timeout: A floating point number specifying the socket timeout in
                    seconds. None means to use the default which is 30 seconds.
    :param retry_wait: A floating point number specifying how many seconds to
                       wait between each retry. None means to use the default
                       which is 5 seconds.
    :param services: A list of mDNS services to try to connect to. If present,
                     parameters host and port are ignored and host and port are
                     instead resolved through mDNS. The list of services may be
                     modified, for example if speaker group leadership is handed
                     over. SocketClient will catch modifications to the list when
                     attempting reconnect.
    :param zconf: A zeroconf instance, needed if a list of services is passed.
                  The zeroconf instance may be obtained from the browser returned by
                  pychromecast.start_discovery().
    """

    # pylint: disable-next=too-many-arguments
    def __init__(
        self,
        *,
        cast_type,
        tries,
        timeout,
        retry_wait,
        services,
        zconf,
    ):
        super().__init__()

        self.daemon = True

        self.logger = logging.getLogger(__name__)

        self._force_recon = False

        self.cast_type = cast_type
        self.fn = None  # pylint:disable=invalid-name
        self.tries = tries
        self.timeout = timeout or TIMEOUT_TIME
        self.retry_wait = retry_wait or RETRY_TIME
        self.services = services
        self.zconf = zconf

        self.host = "unknown"
        self.port = 8009

        self.source_id = "sender-0"
        self.stop = threading.Event()
        # socketpair used to interrupt the worker thread
        self.socketpair = socket.socketpair()

        self.app_namespaces = []
        self.destination_id = None
        self.session_id = None
        self._request_id = 0
        # dict mapping requestId on threading.Event objects
        self._request_callbacks = {}
        self._open_channels = []

        self.connecting = True
        self.first_connection = True
        self.socket = None

        # dict mapping namespace on Controller objects
        self._handlers = defaultdict(set)
        self._connection_listeners = []

        self.receiver_controller = ReceiverController(cast_type)
        self.media_controller = MediaController()
        self.heartbeat_controller = HeartbeatController()

        self.register_handler(self.heartbeat_controller)
        self.register_handler(ConnectionController())
        self.register_handler(self.receiver_controller)
        self.register_handler(self.media_controller)

        self.receiver_controller.register_status_listener(self)

    def initialize_connection(
        self,
    ):  # pylint:disable=too-many-statements, too-many-branches
        """Initialize a socket to a Chromecast, retrying as necessary."""
        tries = self.tries

        if self.socket is not None:
            self.socket.close()
            self.socket = None

        # Make sure nobody is blocking.
        for callback in self._request_callbacks.values():
            callback["event"].set()

        self.app_namespaces = []
        self.destination_id = None
        self.session_id = None
        self._request_id = 0
        self._request_callbacks = {}
        self._open_channels = []

        self.connecting = True
        retry_log_fun = self.logger.error

        # Dict keeping track of individual retry delay for each named service
        retries = {}

        def mdns_backoff(service, retry):
            """Exponentional backoff for service name mdns lookups."""
            now = time.time()
            retry["next_retry"] = now + retry["delay"]
            retry["delay"] = min(retry["delay"] * 2, 300)
            retries[service] = retry

        while not self.stop.is_set() and (
            tries is None or tries > 0
        ):  # pylint:disable=too-many-nested-blocks
            # Prune retries dict
            retries = {
                key: retries[key]
                for key in self.services.copy()
                if (key is not None and key in retries)
            }

            for service in self.services.copy():
                now = time.time()
                retry = retries.get(
                    service, {"delay": self.retry_wait, "next_retry": now}
                )
                if now < retry["next_retry"]:
                    continue
                try:
                    self.socket = new_socket()
                    self.socket.settimeout(self.timeout)
                    self._report_connection_status(
                        ConnectionStatus(
                            CONNECTION_STATUS_CONNECTING,
                            NetworkAddress(self.host, self.port),
                        )
                    )
                    # Resolve the service name.
                    host = None
                    port = None
                    host, port, service_info = get_host_from_service(
                        service, self.zconf
                    )
                    if host and port:
                        if service_info:
                            try:
                                self.fn = service_info.properties[b"fn"].decode("utf-8")
                            except (AttributeError, KeyError, UnicodeError):
                                pass
                        self.logger.debug(
                            "[%s(%s):%s] Resolved service %s to %s:%s",
                            self.fn or "",
                            self.host,
                            self.port,
                            service,
                            host,
                            port,
                        )
                        self.host = host
                        self.port = port
                    else:
                        self.logger.debug(
                            "[%s(%s):%s] Failed to resolve service %s",
                            self.fn or "",
                            self.host,
                            self.port,
                            service,
                        )
                        self._report_connection_status(
                            ConnectionStatus(
                                CONNECTION_STATUS_FAILED_RESOLVE,
                                NetworkAddress(service, None),
                            )
                        )
                        mdns_backoff(service, retry)
                        # If zeroconf fails to receive the necessary data,
                        # try next service
                        continue

                    self.logger.debug(
                        "[%s(%s):%s] Connecting to %s:%s",
                        self.fn or "",
                        self.host,
                        self.port,
                        self.host,
                        self.port,
                    )
                    self.socket.connect((self.host, self.port))
                    context = ssl.SSLContext()
                    self.socket = context.wrap_socket(self.socket)
                    self.connecting = False
                    self._force_recon = False
                    self._report_connection_status(
                        ConnectionStatus(
                            CONNECTION_STATUS_CONNECTED,
                            NetworkAddress(self.host, self.port),
                        )
                    )
                    self.receiver_controller.update_status()
                    self.heartbeat_controller.ping()
                    self.heartbeat_controller.reset()

                    if self.first_connection:
                        self.first_connection = False
                        self.logger.debug(
                            "[%s(%s):%s] Connected!",
                            self.fn or "",
                            self.host,
                            self.port,
                        )
                    else:
                        self.logger.info(
                            "[%s(%s):%s] Connection reestablished!",
                            self.fn or "",
                            self.host,
                            self.port,
                        )
                    return

                # OSError raised if connecting to the socket fails, NotConnected raised
                # if another thread tries - and fails - to send a message before the
                # calls to receiver_controller and heartbeat_controller.
                except (OSError, NotConnected) as err:
                    self.connecting = True
                    if self.stop.is_set():
                        self.logger.error(
                            "[%s(%s):%s] Failed to connect: %s. aborting due to stop signal.",
                            self.fn or "",
                            self.host,
                            self.port,
                            err,
                        )
                        raise ChromecastConnectionError("Failed to connect") from err

                    self._report_connection_status(
                        ConnectionStatus(
                            CONNECTION_STATUS_FAILED,
                            NetworkAddress(self.host, self.port),
                        )
                    )
                    if service is not None:
                        retry_log_fun(
                            "[%s(%s):%s] Failed to connect to service %s, retrying in %.1fs",
                            self.fn or "",
                            self.host,
                            self.port,
                            service,
                            retry["delay"],
                        )
                        mdns_backoff(service, retry)
                    else:
                        retry_log_fun(
                            "[%s(%s):%s] Failed to connect, retrying in %.1fs",
                            self.fn or "",
                            self.host,
                            self.port,
                            self.retry_wait,
                        )
                    retry_log_fun = self.logger.debug

            # Only sleep if we have another retry remaining
            if tries is None or tries > 1:
                self.logger.debug(
                    "[%s(%s):%s] Not connected, sleeping for %.1fs. Services: %s",
                    self.fn or "",
                    self.host,
                    self.port,
                    self.retry_wait,
                    self.services,
                )
                time.sleep(self.retry_wait)

            if tries:
                tries -= 1

        self.stop.set()
        self.logger.error(
            "[%s(%s):%s] Failed to connect. No retries.",
            self.fn or "",
            self.host,
            self.port,
        )
        raise ChromecastConnectionError("Failed to connect")

    def connect(self):
        """Connect socket connection to Chromecast device.

        Must only be called if the worker thread will not be started.
        """
        try:
            self.initialize_connection()
        except ChromecastConnectionError:
            self._report_connection_status(
                ConnectionStatus(
                    CONNECTION_STATUS_DISCONNECTED, NetworkAddress(self.host, self.port)
                )
            )
            return

    def disconnect(self):
        """Disconnect socket connection to Chromecast device"""
        self.stop.set()
        try:
            # Write to the socket to interrupt the worker thread
            self.socketpair[1].send(b"x")
        except socket.error:
            # The socketpair may already be closed during shutdown, ignore it
            pass

    def register_handler(self, handler: BaseController):
        """Register a new namespace handler."""
        self._handlers[handler.namespace].add(handler)

        handler.registered(self)

    def unregister_handler(self, handler: BaseController):
        """Register a new namespace handler."""
        if (
            handler.namespace in self._handlers
            and handler in self._handlers[handler.namespace]
        ):
            self._handlers[handler.namespace].remove(handler)

        handler.unregistered()

    def new_cast_status(self, cast_status):
        """Called when a new cast status has been received."""
        new_channel = self.destination_id != cast_status.transport_id

        if new_channel:
            self.disconnect_channel(self.destination_id)

        self.app_namespaces = cast_status.namespaces
        self.destination_id = cast_status.transport_id
        self.session_id = cast_status.session_id

        if new_channel:
            # If any of the namespaces of the new app are supported
            # we will automatically connect to it to receive updates
            for namespace in self.app_namespaces:
                if namespace in self._handlers:
                    self._ensure_channel_connected(self.destination_id)
                    for handler in self._handlers[namespace]:
                        handler.channel_connected()

    def _gen_request_id(self):
        """Generates a unique request id."""
        self._request_id += 1

        return self._request_id

    @property
    def is_connected(self):
        """
        Returns True if the client is connected, False if it is stopped
        (or trying to connect).
        """
        return not self.connecting

    @property
    def is_stopped(self):
        """
        Returns True if the connection has been stopped, False if it is
        running.
        """
        return self.stop.is_set()

    def run(self):
        """Connect to the cast and start polling the socket."""
        try:
            self.initialize_connection()
        except ChromecastConnectionError:
            self._report_connection_status(
                ConnectionStatus(
                    CONNECTION_STATUS_DISCONNECTED, NetworkAddress(self.host, self.port)
                )
            )
            return

        self.heartbeat_controller.reset()
        self.logger.debug("Thread started...")
        while not self.stop.is_set():
            try:
                if self.run_once(timeout=POLL_TIME_BLOCKING) == 1:
                    break
            except Exception:  # pylint: disable=broad-except
                self._force_recon = True
                self.logger.exception(
                    "[%s(%s):%s] Unhandled exception in worker thread, attempting reconnect",
                    self.fn or "",
                    self.host,
                    self.port,
                )

        self.logger.debug("Thread done...")
        # Clean up
        self._cleanup()

    def run_once(self, timeout=POLL_TIME_NON_BLOCKING):
        """
        Use run_once() in your own main loop after you
        receive something on the socket (get_socket()).
        """
        # pylint: disable=too-many-branches, too-many-return-statements

        try:
            if not self._check_connection():
                return 0
        except ChromecastConnectionError:
            return 1

        # poll the socket, as well as the socketpair to allow us to be interrupted
        rlist = [self.socket, self.socketpair[0]]
        try:
            can_read, _, _ = select.select(rlist, [], [], timeout)
        except (ValueError, OSError) as exc:
            self.logger.error(
                "[%s(%s):%s] Error in select call: %s",
                self.fn or "",
                self.host,
                self.port,
                exc,
            )
            self._force_recon = True
            return 0

        # read messages from chromecast
        message = data = None
        if self.socket in can_read and not self._force_recon:
            try:
                message = self._read_message()
            except InterruptLoop as exc:
                if self.stop.is_set():
                    self.logger.info(
                        "[%s(%s):%s] Stopped while reading message, disconnecting.",
                        self.fn or "",
                        self.host,
                        self.port,
                    )
                else:
                    self.logger.error(
                        "[%s(%s):%s] Interruption caught without being stopped: %s",
                        self.fn or "",
                        self.host,
                        self.port,
                        exc,
                    )
                return 1
            except ssl.SSLError as exc:
                if exc.errno == ssl.SSL_ERROR_EOF:
                    if self.stop.is_set():
                        return 1
                raise
            except socket.error:
                self._force_recon = True
                self.logger.error(
                    "[%s(%s):%s] Error reading from socket.",
                    self.fn or "",
                    self.host,
                    self.port,
                )
            else:
                data = _dict_from_message_payload(message)

        if self.socketpair[0] in can_read:
            # Clear the socket's buffer
            self.socketpair[0].recv(128)

        # If we are stopped after receiving a message we skip the message
        # and tear down the connection
        if self.stop.is_set():
            return 1

        if not message:
            return 0

        # See if any handlers will accept this message
        self._route_message(message, data)

        if REQUEST_ID in data:
            callback = self._request_callbacks.pop(data[REQUEST_ID], None)
            if callback is not None:
                event = callback["event"]
                callback["response"] = data
                function = callback["function"]
                event.set()
                if function:
                    function(data)

        return 0

    def get_socket(self):
        """
        Returns the socket of the connection to use it in you own
        main loop.
        """
        return self.socket

    def _check_connection(self):
        """
        Checks if the connection is active, and if not reconnect

        :return: True if the connection is active, False if the connection was
                 reset.
        """
        # check if connection is expired
        reset = False
        if self._force_recon:
            self.logger.warning(
                "[%s(%s):%s] Error communicating with socket, resetting connection",
                self.fn or "",
                self.host,
                self.port,
            )
            reset = True

        elif self.heartbeat_controller.is_expired():
            self.logger.warning(
                "[%s(%s):%s] Heartbeat timeout, resetting connection",
                self.fn or "",
                self.host,
                self.port,
            )
            reset = True

        if reset:
            self.receiver_controller.disconnected()
            for channel in self._open_channels:
                self.disconnect_channel(channel)
            self._report_connection_status(
                ConnectionStatus(
                    CONNECTION_STATUS_LOST, NetworkAddress(self.host, self.port)
                )
            )
            try:
                self.initialize_connection()
            except ChromecastConnectionError:
                self.stop.set()
            return False
        return True

    def _route_message(self, message, data: dict):
        """Route message to any handlers on the message namespace"""
        # route message to handlers
        if message.namespace in self._handlers:

            # debug messages
            if message.namespace != NS_HEARTBEAT:
                self.logger.debug(
                    "[%s(%s):%s] Received: %s",
                    self.fn or "",
                    self.host,
                    self.port,
                    _message_to_string(message, data),
                )

            # message handlers
            for handler in self._handlers[message.namespace]:
                try:
                    handled = handler.receive_message(message, data)

                    if not handled:
                        if data.get(REQUEST_ID) not in self._request_callbacks:
                            self.logger.debug(
                                "[%s(%s):%s] Message unhandled: %s",
                                self.fn or "",
                                self.host,
                                self.port,
                                _message_to_string(message, data),
                            )
                except Exception:  # pylint: disable=broad-except
                    self.logger.exception(
                        (
                            "[%s(%s):%s] Exception caught while sending message to "
                            "controller %s: %s"
                        ),
                        self.fn or "",
                        self.host,
                        self.port,
                        type(handler).__name__,
                        _message_to_string(message, data),
                    )

        else:
            self.logger.debug(
                "[%s(%s):%s] Received unknown namespace: %s",
                self.fn or "",
                self.host,
                self.port,
                _message_to_string(message, data),
            )

    def _cleanup(self):
        """Cleanup open channels and handlers"""
        for channel in self._open_channels:
            try:
                self.disconnect_channel(channel)
            except Exception:  # pylint: disable=broad-except
                pass

        for namespace in self._handlers.values():
            for handler in namespace:
                try:
                    handler.tear_down()
                except Exception:  # pylint: disable=broad-except
                    pass

        if self.socket is not None:
            try:
                self.socket.close()
            except Exception:  # pylint: disable=broad-except
                self.logger.exception(
                    "[%s(%s):%s] _cleanup", self.fn or "", self.host, self.port
                )
        self._report_connection_status(
            ConnectionStatus(
                CONNECTION_STATUS_DISCONNECTED, NetworkAddress(self.host, self.port)
            )
        )

        self.socketpair[0].close()
        self.socketpair[1].close()

        self.connecting = True

    def _report_connection_status(self, status):
        """Report a change in the connection status to any listeners"""
        for listener in self._connection_listeners:
            try:
                self.logger.debug(
                    "[%s(%s):%s] connection listener: %x (%s) %s",
                    self.fn or "",
                    self.host,
                    self.port,
                    id(listener),
                    type(listener).__name__,
                    status,
                )
                listener.new_connection_status(status)
            except Exception:  # pylint: disable=broad-except
                self.logger.exception(
                    "[%s(%s):%s] Exception thrown when calling connection listener",
                    self.fn or "",
                    self.host,
                    self.port,
                )

    def _read_bytes_from_socket(self, msglen):
        """Read bytes from the socket."""
        chunks = []
        bytes_recd = 0
        while bytes_recd < msglen:
            if self.stop.is_set():
                raise InterruptLoop("Stopped while reading from socket")
            try:
                chunk = self.socket.recv(min(msglen - bytes_recd, 2048))
                if chunk == b"":
                    raise socket.error("socket connection broken")
                chunks.append(chunk)
                bytes_recd += len(chunk)
            except socket.timeout:
                self.logger.debug(
                    "[%s(%s):%s] timeout in : _read_bytes_from_socket",
                    self.fn or "",
                    self.host,
                    self.port,
                )
                continue
            except ssl.SSLError as exc:
                # Support older ssl implementations which does not raise
                # socket.timeout on timeouts
                if _is_ssl_timeout(exc):
                    self.logger.debug(
                        "[%s(%s):%s] ssl timeout in : _read_bytes_from_socket",
                        self.fn or "",
                        self.host,
                        self.port,
                    )
                    continue
                raise
        return b"".join(chunks)

    def _read_message(self):
        """Reads a message from the socket and converts it to a message."""
        # first 4 bytes is Big-Endian payload length
        payload_info = self._read_bytes_from_socket(4)
        read_len = unpack(">I", payload_info)[0]

        # now read the payload
        payload = self._read_bytes_from_socket(read_len)

        message = cast_channel_pb2.CastMessage()
        message.ParseFromString(payload)

        return message

    # pylint: disable=too-many-arguments
    def send_message(
        self,
        destination_id,
        namespace,
        data,
        inc_session_id=False,
        callback_function=False,
        no_add_request_id=False,
        force=False,
    ):
        """Send a message to the Chromecast."""

        # namespace is a string containing namespace
        # data is a dict that will be converted to json
        # wait_for_response only works if we have a request id

        # If channel is not open yet, connect to it.
        self._ensure_channel_connected(destination_id)

        request_id = None
        if not no_add_request_id:
            request_id = self._gen_request_id()
            data[REQUEST_ID] = request_id

        if inc_session_id:
            data[SESSION_ID] = self.session_id

        msg = cast_channel_pb2.CastMessage()

        msg.protocol_version = msg.CASTV2_1_0  # pylint: disable=no-member
        msg.source_id = self.source_id
        msg.destination_id = destination_id
        msg.payload_type = (
            cast_channel_pb2.CastMessage.STRING  # pylint: disable=no-member
        )
        msg.namespace = namespace
        msg.payload_utf8 = _json_to_payload(data)

        # prepend message with Big-Endian 4 byte payload size
        be_size = pack(">I", msg.ByteSize())

        # Log all messages except heartbeat
        if msg.namespace != NS_HEARTBEAT:  # pylint: disable=no-member
            self.logger.debug(
                "[%s(%s):%s] Sending: %s",
                self.fn or "",
                self.host,
                self.port,
                _message_to_string(msg, data),
            )

        if not force and self.stop.is_set():
            raise PyChromecastStopped("Socket client's thread is stopped.")
        if not self.connecting and not self._force_recon:
            try:
                if callback_function:
                    if not no_add_request_id:
                        self._request_callbacks[request_id] = {
                            "event": threading.Event(),
                            "response": None,
                            "function": callback_function,
                        }
                    else:
                        callback_function(None)
                self.socket.sendall(be_size + msg.SerializeToString())
            except socket.error:
                self._request_callbacks.pop(request_id, None)
                self._force_recon = True
                self.logger.info(
                    "[%s(%s):%s] Error writing to socket.",
                    self.fn or "",
                    self.host,
                    self.port,
                )
        else:
            raise NotConnected(f"Chromecast {self.host}:{self.port} is connecting...")

    def send_platform_message(
        self,
        namespace,
        message,
        inc_session_id=False,
        callback_function_param=False,
        no_add_request_id=False,
    ):
        """Helper method to send a message to the platform."""
        return self.send_message(
            PLATFORM_DESTINATION_ID,
            namespace,
            message,
            inc_session_id,
            callback_function_param,
            no_add_request_id=no_add_request_id,
        )

    def send_app_message(
        self,
        namespace,
        message,
        inc_session_id=False,
        callback_function_param=False,
        no_add_request_id=False,
    ):
        """Helper method to send a message to current running app."""
        if namespace not in self.app_namespaces:
            raise UnsupportedNamespace(
                f"Namespace {namespace} is not supported by current app. "
                f"Supported are {', '.join(self.app_namespaces)}"
            )

        return self.send_message(
            self.destination_id,
            namespace,
            message,
            inc_session_id,
            callback_function_param,
            no_add_request_id=no_add_request_id,
        )

    def register_connection_listener(self, listener: ConnectionStatusListener):
        """Register a connection listener for when the socket connection
        changes. Listeners will be called with
        listener.new_connection_status(status)"""
        self._connection_listeners.append(listener)

    def _ensure_channel_connected(self, destination_id):
        """Ensure we opened a channel to destination_id."""
        if destination_id not in self._open_channels:
            self._open_channels.append(destination_id)

            self.send_message(
                destination_id,
                NS_CONNECTION,
                {
                    MESSAGE_TYPE: TYPE_CONNECT,
                    "origin": {},
                    "userAgent": "PyChromecast",
                    "senderInfo": {
                        "sdkType": 2,
                        "version": "15.605.1.3",
                        "browserVersion": "44.0.2403.30",
                        "platform": 4,
                        "systemVersion": "Macintosh; Intel Mac OS X10_10_3",
                        "connectionType": 1,
                    },
                },
                no_add_request_id=True,
            )

    def disconnect_channel(self, destination_id):
        """Disconnect a channel with destination_id."""
        if destination_id in self._open_channels:
            try:
                self.send_message(
                    destination_id,
                    NS_CONNECTION,
                    {MESSAGE_TYPE: TYPE_CLOSE, "origin": {}},
                    no_add_request_id=True,
                    force=True,
                )
            except NotConnected:
                pass
            except Exception:  # pylint: disable=broad-except
                self.logger.exception(
                    "[%s(%s):%s] Exception", self.fn or "", self.host, self.port
                )

            self._open_channels.remove(destination_id)

            self.handle_channel_disconnected()

    def handle_channel_disconnected(self):
        """Handles a channel being disconnected."""
        for namespace in self.app_namespaces:
            if namespace in self._handlers:
                for handler in self._handlers[namespace]:
                    handler.channel_disconnected()

        self.app_namespaces = []
        self.destination_id = None
        self.session_id = None


class ConnectionController(BaseController):
    """Controller to respond to connection messages."""

    def __init__(self):
        super().__init__(NS_CONNECTION)

    def receive_message(self, message, data: dict):
        """
        Called when a message is received.

        data is message.payload_utf8 interpreted as a JSON dict.
        """
        if self._socket_client.is_stopped:
            return True

        if data[MESSAGE_TYPE] == TYPE_CLOSE:
            # The cast device is asking us to acknowledge closing this channel.
            self._socket_client.disconnect_channel(message.source_id)

            # Schedule a status update so that a channel is created.
            self._socket_client.receiver_controller.update_status()

            return True

        return False


class HeartbeatController(BaseController):
    """Controller to respond to heartbeat messages."""

    def __init__(self):
        super().__init__(NS_HEARTBEAT, target_platform=True)
        self.last_ping = 0
        self.last_pong = time.time()

    def receive_message(self, _message, data: dict):
        """
        Called when a heartbeat message is received.

        data is message.payload_utf8 interpreted as a JSON dict.
        """
        if self._socket_client.is_stopped:
            return True

        if data[MESSAGE_TYPE] == TYPE_PING:
            try:
                self._socket_client.send_message(
                    PLATFORM_DESTINATION_ID,
                    self.namespace,
                    {MESSAGE_TYPE: TYPE_PONG},
                    no_add_request_id=True,
                )
            except PyChromecastStopped:
                self._socket_client.logger.debug(
                    "Heartbeat error when sending response, "
                    "Chromecast connection has stopped"
                )

            return True

        if data[MESSAGE_TYPE] == TYPE_PONG:
            self.reset()
            return True

        return False

    def ping(self):
        """Send a ping message."""
        self.last_ping = time.time()
        try:
            self.send_message({MESSAGE_TYPE: TYPE_PING})
        except NotConnected:
            self._socket_client.logger.error(
                "Chromecast is disconnected. Cannot ping until reconnected."
            )

    def reset(self):
        """Reset expired counter."""
        self.last_pong = time.time()

    def is_expired(self):
        """Indicates if connection has expired."""
        if time.time() - self.last_ping > HB_PING_TIME:
            self.ping()

        return (time.time() - self.last_pong) > HB_PING_TIME + HB_PONG_TIME


def new_socket():
    """
    Create a new socket with OS-specific parameters

    Try to set SO_REUSEPORT for BSD-flavored systems if it's an option.
    Catches errors if not.
    """
    new_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    new_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        # noinspection PyUnresolvedReferences
        reuseport = socket.SO_REUSEPORT
    except AttributeError:
        pass
    else:
        try:
            new_sock.setsockopt(socket.SOL_SOCKET, reuseport, 1)
        except (OSError, socket.error) as err:
            # OSError on python 3, socket.error on python 2
            if err.errno != errno.ENOPROTOOPT:
                raise

    return new_sock
