"""
Module to interact with the ChromeCast via protobuf-over-socket.

Big thanks goes out to Fred Clift <fred@clift.org> who build the first
version of this code: https://github.com/minektur/chromecast-python-poc.
Without him this would not have been possible.
"""

# pylint: disable=too-many-lines
from __future__ import annotations

import abc
from dataclasses import dataclass
import errno
import json
import logging
import select
import socket
import ssl
import threading
import time
from collections import defaultdict
from struct import pack, unpack

import zeroconf

from .controllers import CallbackType, BaseController
from .controllers.media import MediaController
from .controllers.receiver import CastStatus, CastStatusListener, ReceiverController
from .const import MESSAGE_TYPE, REQUEST_ID, SESSION_ID
from .dial import get_host_from_service
from .error import (
    ChromecastConnectionError,
    ControllerNotRegistered,
    UnsupportedNamespace,
    NotConnected,
    PyChromecastStopped,
)

# pylint: disable-next=no-name-in-module
from .generated.cast_channel_pb2 import CastMessage
from .models import HostServiceInfo, MDNSServiceInfo

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
# Check for select poll method
SELECT_HAS_POLL = hasattr(select, "poll")

HB_PING_TIME = 10
HB_PONG_TIME = 10
POLL_TIME_BLOCKING = 5.0
POLL_TIME_NON_BLOCKING = 0.01
TIMEOUT_TIME = 30.0
RETRY_TIME = 5.0


class InterruptLoop(Exception):
    """The chromecast has been manually stopped."""


def _dict_from_message_payload(message: CastMessage) -> dict:
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


def _message_to_string(
    message: CastMessage,
    data: dict | None = None,
) -> str:
    """Gives a string representation of a PB2 message."""
    if data is None:
        data = _dict_from_message_payload(message)

    return (
        f"Message {message.namespace} from {message.source_id} to "
        f"{message.destination_id}: {data or message.payload_utf8}"
    )


@dataclass(frozen=True)
class NetworkAddress:
    """Network address container."""

    address: str
    port: int | None


@dataclass(frozen=True)
class ConnectionStatus:
    """Connection status container."""

    status: str
    address: NetworkAddress | None
    service: HostServiceInfo | MDNSServiceInfo | None


class ConnectionStatusListener(abc.ABC):
    """Listener for receiving connection status events."""

    @abc.abstractmethod
    def new_connection_status(self, status: ConnectionStatus) -> None:
        """Updated connection status."""


# pylint: disable-next=too-many-instance-attributes
class SocketClient(threading.Thread, CastStatusListener):
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
        cast_type: str,
        tries: int | None,
        timeout: float | None,
        retry_wait: float | None,
        services: set[HostServiceInfo | MDNSServiceInfo],
        zconf: zeroconf.Zeroconf | None,
    ) -> None:
        super().__init__()

        self.daemon = True

        self.logger = logging.getLogger(__name__)

        self._force_recon = False

        self.cast_type = cast_type
        self.fn: str | None = None  # pylint:disable=invalid-name
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

        self.app_namespaces: list[str] = []
        self.destination_id: str | None = None
        self.session_id: str | None = None
        self._request_id = 0
        self._request_callbacks: dict[int, CallbackType] = {}
        self._open_channels: list[str] = []

        self.connecting = True
        self.first_connection = True
        self.socket: socket.socket | ssl.SSLSocket | None = None

        # dict mapping namespace on Controller objects
        self._handlers: dict[str, set[BaseController]] = defaultdict(set)
        self._connection_listeners: list[ConnectionStatusListener] = []

        self.receiver_controller = ReceiverController(cast_type)
        self.media_controller = MediaController()
        self.heartbeat_controller = HeartbeatController()

        self.register_handler(self.heartbeat_controller)
        self.register_handler(ConnectionController())
        self.register_handler(self.receiver_controller)
        self.register_handler(self.media_controller)

        self.receiver_controller.register_status_listener(self)

    def initialize_connection(  # pylint:disable=too-many-statements, too-many-branches
        self,
    ) -> None:
        """Initialize a socket to a Chromecast, retrying as necessary."""
        tries = self.tries

        if self.socket is not None:
            self.socket.close()
            self.socket = None

        # Make sure nobody is blocking.
        for callback_function in self._request_callbacks.values():
            callback_function(False, None)

        self.app_namespaces = []
        self.destination_id = None
        self.session_id = None
        self._request_id = 0
        self._request_callbacks = {}
        self._open_channels = []

        self.connecting = True
        retry_log_fun = self.logger.error

        # Dict keeping track of individual retry delay for each named service
        retries: dict[HostServiceInfo | MDNSServiceInfo, dict[str, float]] = {}

        def mdns_backoff(
            service: HostServiceInfo | MDNSServiceInfo,
            retry: dict[str, float],
        ) -> None:
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
                    if self.socket is not None:
                        # If we retry connecting, we need to clean up the socket again
                        self.socket.close()  # type: ignore[unreachable]
                        self.socket = None

                    self.socket = new_socket()
                    self.socket.settimeout(self.timeout)
                    self._report_connection_status(
                        ConnectionStatus(
                            CONNECTION_STATUS_CONNECTING,
                            NetworkAddress(self.host, self.port),
                            None,
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
                                # Mypy does not understand that we catch errors, ignore it
                                self.fn = service_info.properties[b"fn"].decode("utf-8")  # type: ignore[union-attr]
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
                                None,
                                service,
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
                    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                    self.socket = context.wrap_socket(self.socket)
                    self.connecting = False
                    self._force_recon = False
                    self._report_connection_status(
                        ConnectionStatus(
                            CONNECTION_STATUS_CONNECTED,
                            NetworkAddress(self.host, self.port),
                            None,
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
                            None,
                        )
                    )
                    retry_log_fun(
                        "[%s(%s):%s] Failed to connect to service %s, retrying in %.1fs",
                        self.fn or "",
                        self.host,
                        self.port,
                        service,
                        retry["delay"],
                    )
                    mdns_backoff(service, retry)
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

    def disconnect(self) -> None:
        """Disconnect socket connection to Chromecast device"""
        self.stop.set()
        try:
            # Write to the socket to interrupt the worker thread
            self.socketpair[1].send(b"x")
        except socket.error:
            # The socketpair may already be closed during shutdown, ignore it
            pass

    def register_handler(self, handler: BaseController) -> None:
        """Register a new namespace handler."""
        self._handlers[handler.namespace].add(handler)

        handler.registered(self)

    def unregister_handler(self, handler: BaseController) -> None:
        """Register a new namespace handler."""
        if (
            handler.namespace in self._handlers
            and handler in self._handlers[handler.namespace]
        ):
            self._handlers[handler.namespace].remove(handler)

        handler.unregistered()

    def new_cast_status(self, status: CastStatus) -> None:
        """Called when a new cast status has been received."""
        new_channel = self.destination_id != status.transport_id

        if new_channel and self.destination_id is not None:
            self.disconnect_channel(self.destination_id)

        self.app_namespaces = status.namespaces
        self.destination_id = status.transport_id
        self.session_id = status.session_id

        if new_channel and self.destination_id is not None:
            # If any of the namespaces of the new app are supported
            # we will automatically connect to it to receive updates
            for namespace in self.app_namespaces:
                if namespace in self._handlers:
                    self._ensure_channel_connected(self.destination_id)
                    for handler in set(self._handlers[namespace]):
                        handler.channel_connected()

    def _gen_request_id(self) -> int:
        """Generates a unique request id."""
        self._request_id += 1

        return self._request_id

    @property
    def is_connected(self) -> bool:
        """
        Returns True if the client is connected, False if it is stopped
        (or trying to connect).
        """
        return not self.connecting

    @property
    def is_stopped(self) -> bool:
        """
        Returns True if the connection has been stopped, False if it is
        running.
        """
        return self.stop.is_set()

    def run(self) -> None:
        """Connect to the cast and start polling the socket."""
        try:
            self.initialize_connection()
        except ChromecastConnectionError:
            self._report_connection_status(
                ConnectionStatus(
                    CONNECTION_STATUS_DISCONNECTED,
                    NetworkAddress(self.host, self.port),
                    None,
                )
            )
            return

        self.heartbeat_controller.reset()
        self.logger.debug("Thread started...")
        while not self.stop.is_set():
            try:
                if self._run_once(timeout=POLL_TIME_BLOCKING) == 1:
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

    def _run_once(self, timeout: float = POLL_TIME_NON_BLOCKING) -> int:
        """Receive from the socket and handle data."""
        # pylint: disable=too-many-branches, too-many-statements, too-many-return-statements

        try:
            if not self._check_connection():
                return 0
        except ChromecastConnectionError:
            return 1

        # A connection has been established at this point by self._check_connection
        assert self.socket is not None

        # poll the socket, as well as the socketpair to allow us to be interrupted
        rlist = [self.socket, self.socketpair[0]]
        try:
            if SELECT_HAS_POLL is True:
                # Map file descriptors to socket objects because select.select does not support fd > 1024
                # https://stackoverflow.com/questions/14250751/how-to-increase-filedescriptors-range-in-python-select
                fd_to_socket = {rlist_item.fileno(): rlist_item for rlist_item in rlist}

                poll_obj = select.poll()
                for poll_fd in rlist:
                    poll_obj.register(poll_fd, select.POLLIN)
                poll_result = poll_obj.poll(timeout * 1000)  # timeout in milliseconds
                can_read = [fd_to_socket[fd] for fd, _status in poll_result]
            else:
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

        # read message from chromecast
        message = None
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

        if REQUEST_ID in data and data[REQUEST_ID] in self._request_callbacks:
            self._request_callbacks.pop(data[REQUEST_ID])(True, data)

        return 0

    def _check_connection(self) -> bool:
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
                    CONNECTION_STATUS_LOST, NetworkAddress(self.host, self.port), None
                )
            )
            try:
                self.initialize_connection()
            except ChromecastConnectionError:
                self.stop.set()
            return False
        return True

    def _route_message(self, message: CastMessage, data: dict) -> None:
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
            for handler in set(self._handlers[message.namespace]):
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

    def _cleanup(self) -> None:
        """Cleanup open channels and handlers"""
        for channel in self._open_channels:
            try:
                self.disconnect_channel(channel)
            except Exception:  # pylint: disable=broad-except
                pass

        for handlers in self._handlers.values():
            for handler in set(handlers):
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
                CONNECTION_STATUS_DISCONNECTED,
                NetworkAddress(self.host, self.port),
                None,
            )
        )

        self.socketpair[0].close()
        self.socketpair[1].close()

        self.connecting = True

    def _report_connection_status(self, status: ConnectionStatus) -> None:
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

    def _read_bytes_from_socket(self, msglen: int) -> bytes:
        """Read bytes from the socket."""
        # It is a programming error if this is called when we don't have a socket
        assert self.socket is not None

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
            except TimeoutError:
                self.logger.debug(
                    "[%s(%s):%s] timeout in : _read_bytes_from_socket",
                    self.fn or "",
                    self.host,
                    self.port,
                )
                continue
        return b"".join(chunks)

    def _read_message(self) -> CastMessage:
        """Reads a message from the socket and converts it to a message."""
        # first 4 bytes is Big-Endian payload length
        payload_info = self._read_bytes_from_socket(4)
        read_len = unpack(">I", payload_info)[0]

        # now read the payload
        payload = self._read_bytes_from_socket(read_len)

        message = CastMessage()
        message.ParseFromString(payload)

        return message

    # pylint: disable=too-many-arguments, too-many-branches
    def send_message(
        self,
        destination_id: str,
        namespace: str,
        data: dict,
        *,
        inc_session_id: bool = False,
        callback_function: CallbackType | None = None,
        no_add_request_id: bool = False,
        force: bool = False,
    ) -> None:
        """Send a message to the Chromecast."""

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

        msg = CastMessage()

        msg.protocol_version = msg.CASTV2_1_0
        msg.source_id = self.source_id
        msg.destination_id = destination_id
        msg.payload_type = CastMessage.STRING
        msg.namespace = namespace
        msg.payload_utf8 = json.dumps(data, ensure_ascii=False)

        # prepend message with Big-Endian 4 byte payload size
        be_size = pack(">I", msg.ByteSize())

        # Log all messages except heartbeat
        if msg.namespace != NS_HEARTBEAT:
            self.logger.debug(
                "[%s(%s):%s] Sending: %s",
                self.fn or "",
                self.host,
                self.port,
                _message_to_string(msg, data),
            )

        if not force and self.stop.is_set():
            if callback_function:
                callback_function(False, None)
            raise PyChromecastStopped("Socket client's thread is stopped.")
        if not self.connecting and not self._force_recon:
            # We have a socket
            assert self.socket is not None

            try:
                if callback_function:
                    if not no_add_request_id:
                        self._request_callbacks[request_id] = callback_function
                    else:
                        callback_function(True, None)
                self.socket.sendall(be_size + msg.SerializeToString())
            except socket.error:
                if callback_function:
                    callback_function(False, None)
                if not no_add_request_id:
                    self._request_callbacks.pop(request_id, None)
                self._force_recon = True
                self.logger.info(
                    "[%s(%s):%s] Error writing to socket.",
                    self.fn or "",
                    self.host,
                    self.port,
                )
        else:
            if callback_function:
                callback_function(False, None)
            raise NotConnected(f"Chromecast {self.host}:{self.port} is connecting...")

    def send_platform_message(
        self,
        namespace: str,
        message: dict,
        *,
        inc_session_id: bool = False,
        callback_function: CallbackType | None = None,
        no_add_request_id: bool = False,
    ) -> None:
        """Helper method to send a message to the platform."""
        return self.send_message(
            PLATFORM_DESTINATION_ID,
            namespace,
            message,
            inc_session_id=inc_session_id,
            callback_function=callback_function,
            no_add_request_id=no_add_request_id,
        )

    def send_app_message(
        self,
        namespace: str,
        message: dict,
        *,
        inc_session_id: bool = False,
        callback_function: CallbackType | None = None,
        no_add_request_id: bool = False,
    ) -> None:
        """Helper method to send a message to current running app."""
        if namespace not in self.app_namespaces:
            if callback_function:
                callback_function(False, None)
            raise UnsupportedNamespace(
                f"Namespace {namespace} is not supported by current app. "
                f"Supported are {', '.join(self.app_namespaces)}"
            )

        if self.destination_id is None:
            if callback_function:
                callback_function(False, None)
            raise NotConnected(
                "Attempting send a message when destination_id is not set"
            )

        return self.send_message(
            self.destination_id,
            namespace,
            message,
            inc_session_id=inc_session_id,
            callback_function=callback_function,
            no_add_request_id=no_add_request_id,
        )

    def register_connection_listener(self, listener: ConnectionStatusListener) -> None:
        """Register a connection listener for when the socket connection
        changes. Listeners will be called with
        listener.new_connection_status(status)"""
        self._connection_listeners.append(listener)

    def _ensure_channel_connected(self, destination_id: str) -> None:
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

    def disconnect_channel(self, destination_id: str) -> None:
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

    def handle_channel_disconnected(self) -> None:
        """Handles a channel being disconnected."""
        for namespace in self.app_namespaces:
            if namespace in self._handlers:
                for handler in set(self._handlers[namespace]):
                    handler.channel_disconnected()

        self.app_namespaces = []
        self.destination_id = None
        self.session_id = None


class ConnectionController(BaseController):
    """Controller to respond to connection messages."""

    def __init__(self) -> None:
        super().__init__(NS_CONNECTION)

    def receive_message(self, message: CastMessage, data: dict) -> bool:
        """
        Called when a message is received.

        data is message.payload_utf8 interpreted as a JSON dict.
        """
        if self._socket_client is None:
            raise ControllerNotRegistered

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

    def __init__(self) -> None:
        super().__init__(NS_HEARTBEAT, target_platform=True)
        self.last_ping = 0.0
        self.last_pong = time.time()

    def receive_message(self, _message: CastMessage, data: dict) -> bool:
        """
        Called when a heartbeat message is received.

        data is message.payload_utf8 interpreted as a JSON dict.
        """
        if self._socket_client is None:
            raise ControllerNotRegistered

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

    def ping(self) -> None:
        """Send a ping message."""
        if self._socket_client is None:
            raise ControllerNotRegistered

        self.last_ping = time.time()
        try:
            self.send_message({MESSAGE_TYPE: TYPE_PING})
        except NotConnected:
            self._socket_client.logger.error(
                "Chromecast is disconnected. Cannot ping until reconnected."
            )

    def reset(self) -> None:
        """Reset expired counter."""
        self.last_pong = time.time()

    def is_expired(self) -> bool:
        """Indicates if connection has expired."""
        if time.time() - self.last_ping > HB_PING_TIME:
            self.ping()

        return (time.time() - self.last_pong) > HB_PING_TIME + HB_PONG_TIME


def new_socket() -> socket.socket:
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
