"""
Module to interact with the ChromeCast via protobuf-over-socket.

Big thanks goes out to Fred Clift <fred@clift.org> who build the first
version of this code: https://github.com/minektur/chromecast-python-poc.
Without him this would not have been possible.
"""

# pylint: disable=too-many-lines

import abc
import json
import logging
import selectors
import socket
import ssl
import threading
import time
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from struct import pack, unpack
from typing import Any
from uuid import UUID

from cryptography import x509
import zeroconf

from .config import APP_AUDIBLE
from .const import (
    CAST_TYPE_GROUP,
    MESSAGE_TYPE,
    PLATFORM_DESTINATION_ID,
    REQUEST_ID,
    SESSION_ID,
)
from .controllers import BaseController, CallbackType, Listeners
from .controllers.heartbeat import NS_HEARTBEAT, HeartbeatController
from .controllers.media import MediaController
from .controllers.receiver import CastStatus, CastStatusListener, ReceiverController
from .device_auth import (
    DEVICE_AUTH_TIMEOUT,
    DeviceAuthFailureClass,
    DeviceAuthResult,
    DeviceAuthStatus,
    authenticate,
    verify_group_leader,
    verify_not_group_endpoint,
)
from .dial import get_host_from_service
from .error import (
    ChromecastConnectionError,
    ChromecastConnectionClosed,
    ControllerNotRegistered,
    DeviceAuthenticationError,
    NotConnected,
    PyChromecastStopped,
    UnsupportedNamespace,
)

# pylint: disable-next=no-name-in-module
from .generated.cast_channel_pb2 import CastMessage
from .models import HostServiceInfo, MDNSServiceInfo

NS_CONNECTION = "urn:x-cast:com.google.cast.tp.connection"

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
# The device failed device authentication and was not talked to, the result is
# in ConnectionStatus.device_auth. The connection is retried like after a
# network failure. Consumers should apply a grace period before surfacing a
# failure of class DeviceAuthFailureClass.WRONG_IDENTITY, it's expected for a
# while after an IP address change or a group leader change.
CONNECTION_STATUS_FAILED_AUTH = "FAILED_AUTH"
# The socket connection was lost and needs to be retried
CONNECTION_STATUS_LOST = "LOST"

SELECT_TIMEOUT = 5.0
# Seconds failures which are expected for a while, like a device with the wrong
# identity at a stale address or a group leader change, are only logged at debug
FAILURE_GRACE_PERIOD = 600.0
TIMEOUT_TIME = 30.0
RETRY_TIME = 5.0


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
    # The device authentication result, set for CONNECTED and FAILED_AUTH, see
    # CONNECTION_STATUS_FAILED_AUTH
    device_auth: DeviceAuthResult | None = None


class _SocketClientLogger(logging.LoggerAdapter):
    """Prefixes log messages with the friendly name and address of the cast."""

    def __init__(self, logger: logging.Logger, client: SocketClient) -> None:
        super().__init__(logger)
        self._client = client

    def log(self, level: int, msg: object, *args: object, **kwargs: Any) -> None:
        """Add the prefix, the name and address may change while connecting."""
        if not self.isEnabledFor(level):
            return
        client = self._client
        prefix = f"[{client.fn or ''}({client.host}):{client.port}]"
        if args:
            # The message is formatted with args, the name or a scoped IPv6
            # address may contain %
            prefix = prefix.replace("%", "%%")
        # Skip this frame so records name the real caller
        kwargs["stacklevel"] = kwargs.get("stacklevel", 1) + 1
        self.logger.log(level, f"{prefix} {msg}", *args, **kwargs)


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
    :param device_auth: Authenticate the device on every connect, and don't talk
                        to a device which is not genuine. Set to False to talk to
                        any device, the device's identity is then not verified.
    :param expected_uuid: The UUID of the device or group. If set, a device whose
                          TLS certificate is for another UUID fails
                          authentication, unless cast_type is a group and the
                          device proves it leads the group, see
                          device_auth.verify_group_leader. If None, the identity
                          is not checked.
    :param device_auth_trust_roots: Replaces the bundled Google Cast roots, for
                                    tests.
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
        device_auth: bool = True,
        expected_uuid: UUID | None = None,
        device_auth_trust_roots: Sequence[x509.Certificate] | None = None,
    ) -> None:
        super().__init__()

        self.daemon = True

        self.logger = _SocketClientLogger(logging.getLogger(__name__), self)

        self._force_recon = False

        self.cast_type = cast_type
        self.fn: str | None = None  # pylint:disable=invalid-name
        self.tries = tries
        self.timeout = timeout or TIMEOUT_TIME
        self.retry_wait = retry_wait or RETRY_TIME
        self.services = services
        self.zconf = zconf
        self.device_auth = device_auth
        self.expected_uuid = expected_uuid
        self.device_auth_trust_roots = device_auth_trust_roots
        # The device authentication result of the current or last attempt
        self.device_auth_result: DeviceAuthResult | None = None
        # When the current streak of failures started, and which kinds of
        # failures logged after a grace period were logged in the streak
        self._failure_streak_start: float | None = None
        self._failure_streak_warned = False

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
        self.socket: ssl.SSLSocket | None = None
        # Guards the socket, which isn't thread safe, and the sending state
        self._socket_lock = threading.RLock()
        # Received data not yet parsed into complete messages
        self._recv_buffer = b""
        self.selector = selectors.DefaultSelector()
        self.wakeup_selector_key = self.selector.register(
            self.socketpair[0], selectors.EVENT_READ
        )
        self.remote_selector_key: selectors.SelectorKey | None = None

        # dict mapping namespace on Controller objects
        self._handlers: dict[str, set[BaseController]] = defaultdict(set)
        self._connection_listeners: Listeners[ConnectionStatusListener] = Listeners()

        self.receiver_controller = ReceiverController(cast_type)
        self.media_controller = MediaController()
        self.heartbeat_controller = HeartbeatController()

        self.register_handler(self.heartbeat_controller)
        self.register_handler(ConnectionController())
        self.register_handler(self.receiver_controller)
        self.register_handler(self.media_controller)

        self.receiver_controller.register_status_listener(self)

        if not device_auth:
            self.logger.info(
                "Cast device authentication is disabled; "
                "the identity of the device at %s is not verified",
                services,
            )

    def initialize_connection(  # pylint:disable=too-many-statements, too-many-branches, too-many-locals
        self,
    ) -> None:
        """Initialize a socket to a Chromecast, retrying as necessary."""
        tries = self.tries

        with self._socket_lock:
            self._close_socket()

            callbacks = list(self._request_callbacks.values())
            self._recv_buffer = b""
            self._request_id = 0
            self._request_callbacks = {}
            self._open_channels = []
            self.connecting = True

        # Make sure nobody is blocking.
        for callback_function in callbacks:
            try:
                callback_function(False, None)
            except Exception:  # pylint: disable=broad-except
                self.logger.exception("Unhandled exception in callback function")

        self.app_namespaces = []
        self.destination_id = None
        self.session_id = None

        retry_log_fun = self.logger.info
        auth_log_fun = self.logger.warning

        def log_retry(msg: str, *args: object) -> None:
            """Log a network-like failure, for groups after a grace period."""
            nonlocal retry_log_fun
            if self.cast_type != CAST_TYPE_GROUP:
                retry_log_fun(msg, *args)
                retry_log_fun = self.logger.debug
            # A group leader change closes the group's port on the old leader,
            # and is expected to heal when mDNS finds the new one
            elif self._failure_streak_exceeds_grace():
                self.logger.info(
                    f"{msg} (failing for %.0fs)", *args, self._streak_age()
                )
            else:
                self.logger.debug(msg, *args)

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

        while not self.stop.is_set() and (tries is None or tries > 0):
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
                    self.device_auth_result = None
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
                            except AttributeError, KeyError, UnicodeError:
                                pass
                        self.logger.debug(
                            "Resolved service %s to %s:%s", service, host, port
                        )
                        self.host = host
                        self.port = port
                    else:
                        self.logger.debug("Failed to resolve service %s", service)
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

                    self.logger.debug("Connecting")
                    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                    raw_socket = socket.create_connection(
                        (self.host, self.port), self.timeout
                    )
                    try:
                        tls_socket = context.wrap_socket(raw_socket)
                    except BaseException:
                        raw_socket.close()
                        raise
                    # Authenticate before anything else is sent. While
                    # self.connecting is set, other threads fail to send with
                    # NotConnected. The socket is published, and registered with
                    # the selector, only once the device is authenticated.
                    # Known limitation: disconnect() waits for the handshake, up
                    # to DEVICE_AUTH_TIMEOUT, and twice that if eureka_info is
                    # fetched, like it waits for connecting.
                    try:
                        self.device_auth_result = self._authenticate_device(tls_socket)
                    except BaseException:
                        tls_socket.close()
                        raise
                    self.socket = tls_socket
                    self.remote_selector_key = self.selector.register(
                        self.socket, selectors.EVENT_READ
                    )
                    self.connecting = False
                    self._force_recon = False
                    self._failure_streak_start = None
                    self._failure_streak_warned = False
                    self._report_connection_status(
                        ConnectionStatus(
                            CONNECTION_STATUS_CONNECTED,
                            NetworkAddress(self.host, self.port),
                            None,
                            device_auth=self.device_auth_result,
                        )
                    )
                    self.receiver_controller.update_status()
                    self.heartbeat_controller.ping()
                    self.heartbeat_controller.reset()

                    if self.first_connection:
                        self.first_connection = False
                        self.logger.debug("Connected!")
                    else:
                        self.logger.info("Connection reestablished!")
                    return

                except DeviceAuthenticationError as err:
                    self.connecting = True
                    self.device_auth_result = err.result
                    self._close_socket()
                    if self.stop.is_set():
                        self.logger.debug(
                            "Failed to connect: %s. aborting due to stop signal.", err
                        )
                        raise ChromecastConnectionError("Failed to connect") from err

                    self._report_connection_status(
                        ConnectionStatus(
                            CONNECTION_STATUS_FAILED_AUTH,
                            NetworkAddress(self.host, self.port),
                            None,
                            device_auth=err.result,
                        )
                    )
                    result = err.result
                    failure_class = result.failure_class
                    self._note_failure()
                    if failure_class is DeviceAuthFailureClass.WRONG_IDENTITY:
                        self._log_wrong_identity(result, retry["delay"])
                    elif failure_class is DeviceAuthFailureClass.TRANSIENT:
                        log_retry(
                            "Device authentication with service %s failed: %s (%s), "
                            "retrying in %.1fs",
                            service,
                            result.status,
                            result.detail,
                            retry["delay"],
                        )
                    elif failure_class is DeviceAuthFailureClass.CLOCK:
                        auth_log_fun(
                            "Device authentication failed: %s (%s). Check the "
                            "system clock; if it's correct, the device may need a "
                            "firmware update. Not connecting, retrying in %.1fs",
                            result.status,
                            result.detail,
                            retry["delay"],
                        )
                        auth_log_fun = self.logger.debug
                    else:
                        auth_log_fun(
                            "Device authentication failed, the device may not be a "
                            "genuine Cast device: %s (%s). Not connecting, "
                            "retrying in %.1fs",
                            result.status,
                            result.detail,
                            retry["delay"],
                        )
                        auth_log_fun = self.logger.debug
                    mdns_backoff(service, retry)

                # OSError raised if connecting to the socket fails, NotConnected raised
                # if another thread tries - and fails - to send a message before the
                # calls to receiver_controller and heartbeat_controller.
                except (OSError, NotConnected) as err:
                    self.connecting = True
                    self._close_socket()
                    if self.stop.is_set():
                        self.logger.debug(
                            "Failed to connect: %s. aborting due to stop signal.", err
                        )
                        raise ChromecastConnectionError("Failed to connect") from err

                    self._report_connection_status(
                        ConnectionStatus(
                            CONNECTION_STATUS_FAILED,
                            NetworkAddress(self.host, self.port),
                            None,
                        )
                    )
                    if self.cast_type == CAST_TYPE_GROUP:
                        self._note_failure()
                    log_retry(
                        "Failed to connect to service %s, retrying in %.1fs",
                        service,
                        retry["delay"],
                    )
                    mdns_backoff(service, retry)

            # Only sleep if we have another retry remaining
            if tries is None or tries > 1:
                self.logger.debug(
                    "Not connected, sleeping for %.1fs. Services: %s",
                    self.retry_wait,
                    self.services,
                )
                time.sleep(self.retry_wait)

            if tries:
                tries -= 1

        self.stop.set()
        # The result is reset for every attempt, set if the last one failed auth
        last_result = self.device_auth_result
        if last_result is not None and not last_result.verified:
            self.logger.error(
                "Failed to connect, device authentication failed (%s). No retries.",
                last_result.status,
            )
            raise DeviceAuthenticationError(last_result)
        self.logger.error("Failed to connect. No retries.")
        raise ChromecastConnectionError("Failed to connect")

    def _note_failure(self) -> None:
        """Note a failure, starting a failure streak if none is ongoing."""
        if self._failure_streak_start is None:
            self._failure_streak_start = time.monotonic()

    def _streak_age(self) -> float:
        """Return how long the failure streak has lasted, in seconds."""
        if self._failure_streak_start is None:
            return 0.0
        return time.monotonic() - self._failure_streak_start

    def _failure_streak_exceeds_grace(self) -> bool:
        """Return True once per streak, after the grace period."""
        if self._failure_streak_warned or self._streak_age() <= FAILURE_GRACE_PERIOD:
            return False
        self._failure_streak_warned = True
        return True

    def _log_wrong_identity(self, result: DeviceAuthResult, delay: float) -> None:
        """Log a genuine device with the wrong identity, warn if it persists."""
        expected = (
            f"{self.fn} ({self.expected_uuid})" if self.fn else str(self.expected_uuid)
        )
        msg = (
            "The device at this address is a genuine Cast device but not %s "
            "(it identifies as %s: %s). This can happen after an IP address change "
            "or group leader change; still retrying in %.1fs, failing for %.0fs"
        )
        log_fun = (
            self.logger.warning
            if self._failure_streak_exceeds_grace()
            else self.logger.debug
        )
        log_fun(
            msg, expected, result.tls_cert_cn, result.detail, delay, self._streak_age()
        )

    def _authenticate_device(self, tls_socket: ssl.SSLSocket) -> DeviceAuthResult:
        """Authenticate the device, raise DeviceAuthenticationError on failure."""
        if not self.device_auth:
            return DeviceAuthResult(
                DeviceAuthStatus.DISABLED, "device authentication disabled"
            )
        timeout = min(self.timeout, DEVICE_AUTH_TIMEOUT)
        try:
            result = authenticate(
                tls_socket,
                expected_uuid=self.expected_uuid,
                timeout=timeout,
                trust_roots=self.device_auth_trust_roots,
            )
            # A group is served by its leader, whose certificate names the
            # leader. Any other endpoint, even one labelled a group, must present
            # the expected UUID.
            if (
                result.status is DeviceAuthStatus.UUID_MISMATCH
                and self.cast_type == CAST_TYPE_GROUP
                and self.expected_uuid is not None
            ):
                result = self._verify_group_leader(result, self.expected_uuid, timeout)
            # A device presents its own certificate on the ports of the groups it
            # leads too, don't accept such a port as the device itself
            elif result.uuid_checked and self.port != 8009:
                result = self._verify_not_group_endpoint(result, timeout)
        finally:
            tls_socket.settimeout(self.timeout)
        if not result.verified:
            raise DeviceAuthenticationError(result)
        if result.leader_uuid is not None:
            identity = f", the group leader {result.leader_uuid}"
        elif result.uuid_checked:
            identity = ""
        else:
            identity = " (UUID not checked)"
        self.logger.debug(
            "Device authenticated: %s via %s%s",
            result.device_cert_subject,
            result.trust_root,
            identity,
        )
        return result

    def _verify_group_leader(
        self, result: DeviceAuthResult, group_uuid: UUID, timeout: float
    ) -> DeviceAuthResult:
        """Check the genuine device in result leads the group."""
        attestation = verify_group_leader(
            self.host,
            self.port,
            group_uuid,
            result.device_cert_der,
            timeout=timeout,
        )
        if not attestation.verified:
            return replace(result, status=attestation.status, detail=attestation.detail)
        return replace(
            result,
            status=DeviceAuthStatus.VERIFIED,
            detail=attestation.detail,
            uuid_checked=True,
            leader_uuid=result.tls_cert_uuid,
        )

    def _verify_not_group_endpoint(
        self, result: DeviceAuthResult, timeout: float
    ) -> DeviceAuthResult:
        """Check the device in result doesn't lead a group on self.port."""
        check = verify_not_group_endpoint(
            self.host, self.port, result.device_cert_der, timeout=timeout
        )
        if check.verified:
            return result
        return replace(
            result, status=check.status, detail=check.detail, uuid_checked=False
        )

    def _close_socket(self) -> None:
        """Close the socket to the Chromecast, if any."""
        with self._socket_lock:
            if self.remote_selector_key is not None:
                self.selector.unregister(self.remote_selector_key.fileobj)
                self.remote_selector_key = None
            if self.socket is not None:
                self.socket.close()
                self.socket = None

    def disconnect(self) -> None:
        """Disconnect socket connection to Chromecast device"""
        self.stop.set()
        try:
            # Write to the socket to interrupt the worker thread
            self.socketpair[1].send(b"x")
        except OSError:
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
        # A group member taking over the group's session keeps the transport
        # of the app it ran as a member, but it's a new app
        new_channel = (
            self.destination_id != status.transport_id
            or self.session_id != status.session_id
        )

        if new_channel and self.destination_id is not None:
            self.disconnect_channel(self.destination_id)

        self.app_namespaces = status.namespaces
        self.destination_id = status.transport_id
        self.session_id = status.session_id

        if new_channel and self.destination_id is not None:
            # App quirk: If the Audible app is running, wait 1s after receiving cast status
            # before connecting to the media player channel. This is a workaround for
            # https://github.com/home-assistant-libs/pychromecast/issues/738
            if (
                any(namespace in self._handlers for namespace in self.app_namespaces)
                and self.destination_id not in self._open_channels
                and status.app_id == APP_AUDIBLE
            ):
                self.logger.debug("Detected Audible connection. Sleeping for 1s")
                time.sleep(1)

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
                if self._run_once() == 1:
                    break
            except PyChromecastStopped:
                break
            except Exception:  # pylint: disable=broad-except
                self._force_recon = True
                self.logger.exception(
                    "Unhandled exception in worker thread, attempting reconnect"
                )

        self.logger.debug("Thread done...")
        # Clean up
        self._cleanup()

    def _run_once(self) -> int:
        """Receive from the socket and handle data."""
        # pylint: disable=too-many-branches, too-many-statements, too-many-return-statements

        try:
            if not self._check_connection():
                return 0
        except ChromecastConnectionError:
            return 1

        # A connection has been established at this point by self._check_connection
        assert self.socket is not None

        # Poll the socket and the socketpair, with a timeout of SELECT_TIMEOUT
        # The timeout ensures we call _check_connection often enough to avoid
        # the HeartbeatController from detecting a timeout
        # The socketpair allow us to be interrupted on shutdown without waiting
        # for the SELECT_TIMEOUT timout to expire
        try:
            ready = self.selector.select(SELECT_TIMEOUT)
        except (ValueError, OSError) as exc:
            self.logger.error("Error in select call: %s", exc)
            self._force_recon = True
            return 0

        can_read = {key for key, _ in ready}
        # read messages from chromecast
        messages: list[CastMessage] = []
        if self.remote_selector_key in can_read and not self._force_recon:
            try:
                messages = self._read_messages()
            except ssl.SSLError as exc:
                if exc.errno == ssl.SSL_ERROR_EOF:
                    if self.stop.is_set():
                        return 1
                raise
            except ChromecastConnectionClosed as exc:
                self._force_recon = True
                self.logger.debug("%s", exc)
            except OSError as exc:
                self._force_recon = True
                self.logger.error("Error reading from socket: %s", exc)

        if self.wakeup_selector_key in can_read:
            # Clear the socket's buffer
            self.socketpair[0].recv(128)

        for message in messages:
            # If we are stopped after receiving a message we skip the message
            # and tear down the connection
            if self.stop.is_set():
                return 1

            # See if any handlers will accept this message
            data = _dict_from_message_payload(message)
            self._route_message(message, data)

            # A sender may remove the callback concurrently if writing fails
            if REQUEST_ID in data and (
                callback_function := self._request_callbacks.pop(data[REQUEST_ID], None)
            ):
                callback_function(True, data)

        if self.stop.is_set():
            return 1

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
            self.logger.debug("Forced reconnection")
            reset = True

        elif self.heartbeat_controller.is_expired():
            self.logger.info("Heartbeat timeout, resetting connection")
            reset = True

        if reset:
            self.receiver_controller.disconnected()
            # disconnect_channel removes the channel from the list
            for channel in list(self._open_channels):
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
            if (
                message.namespace != NS_HEARTBEAT
                or self.heartbeat_controller.logger.isEnabledFor(logging.DEBUG)
            ):
                self.logger.debug("Received: %s", _message_to_string(message, data))

            # message handlers
            for handler in set(self._handlers[message.namespace]):
                try:
                    handled = handler.receive_message(message, data)

                    if not handled:
                        if data.get(REQUEST_ID) not in self._request_callbacks:
                            self.logger.debug(
                                "Message unhandled: %s",
                                _message_to_string(message, data),
                            )
                except Exception:  # pylint: disable=broad-except
                    self.logger.exception(
                        "Exception caught while sending message to controller %s: %s",
                        type(handler).__name__,
                        _message_to_string(message, data),
                    )

        else:
            self.logger.debug(
                "Received unknown namespace: %s", _message_to_string(message, data)
            )

    def _cleanup(self) -> None:
        """Cleanup open channels and handlers"""
        # disconnect_channel removes the channel from the list
        for channel in list(self._open_channels):
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

        try:
            self._close_socket()
        except Exception:  # pylint: disable=broad-except
            self.logger.exception("_cleanup")
        self._report_connection_status(
            ConnectionStatus(
                CONNECTION_STATUS_DISCONNECTED,
                NetworkAddress(self.host, self.port),
                None,
            )
        )

        self.socketpair[0].close()
        self.socketpair[1].close()
        self.selector.close()

        self.connecting = True

    def _report_connection_status(self, status: ConnectionStatus) -> None:
        """Report a change in the connection status to any listeners"""
        for listener in self._connection_listeners:
            try:
                self.logger.debug(
                    "connection listener: %x (%s) %s",
                    id(listener),
                    type(listener).__name__,
                    status,
                )
                listener.new_connection_status(status)
            except Exception:  # pylint: disable=broad-except
                self.logger.exception(
                    "Exception thrown when calling connection listener"
                )

    def _read_bytes_from_socket(self) -> bytes:
        """Read one TLS record from the socket without waiting for more.

        Data left in the socket wakes the selector again, which lets senders
        and stop in between reads.
        """
        # It is a programming error if this is called when we don't have a socket
        assert self.socket is not None

        chunks = []
        events = selectors.EVENT_READ
        with self._socket_lock:
            self.socket.settimeout(0)
            try:
                chunk = self.socket.recv(65536)
                if chunk == b"":
                    raise ChromecastConnectionClosed("Connection was closed by remote")
                chunks.append(chunk)
                # Decrypted data is not seen by the selector, only an SSLSocket
                # is read from
                while pending := self.socket.pending():
                    chunks.append(self.socket.recv(pending))
            except ssl.SSLWantReadError:
                pass
            except ssl.SSLWantWriteError:
                # The read is retried when TLS can write what it needs to, also
                # waiting for reads would busy-loop while the socket is readable
                events = selectors.EVENT_WRITE
            finally:
                self.socket.settimeout(self.timeout)

        assert self.remote_selector_key is not None
        if self.remote_selector_key.events != events:
            self.remote_selector_key = self.selector.modify(self.socket, events)

        return b"".join(chunks)

    def _read_messages(self) -> list[CastMessage]:
        """Read the messages available on the socket.

        A partial message is kept until the rest of it has been received.
        """
        self._recv_buffer += self._read_bytes_from_socket()

        messages = []
        # each message is prefixed with its Big-Endian 4 byte length
        while len(self._recv_buffer) >= 4:
            (read_len,) = unpack(">I", self._recv_buffer[:4])
            if len(self._recv_buffer) < 4 + read_len:
                break
            message = CastMessage()
            message.ParseFromString(self._recv_buffer[4 : 4 + read_len])
            self._recv_buffer = self._recv_buffer[4 + read_len :]
            messages.append(message)

        return messages

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

        # Callbacks are called without holding the lock
        try:
            with self._socket_lock:
                sent = self._send_message_locked(
                    destination_id,
                    namespace,
                    data,
                    inc_session_id=inc_session_id,
                    callback_function=callback_function,
                    no_add_request_id=no_add_request_id,
                    force=force,
                )
        except PyChromecastStopped, NotConnected:
            if callback_function:
                callback_function(False, None)
            raise

        if callback_function and (not sent or no_add_request_id):
            callback_function(sent, None)

    def _send_message_locked(
        self,
        destination_id: str,
        namespace: str,
        data: dict,
        *,
        inc_session_id: bool,
        callback_function: CallbackType | None,
        no_add_request_id: bool,
        force: bool,
    ) -> bool:
        """Send a message, the socket lock must be held.

        Returns False if writing to the socket failed.
        """
        # If channel is not open yet, connect to it.
        self._ensure_channel_connected(destination_id)

        request_id = None
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
        if (
            msg.namespace != NS_HEARTBEAT
            or self.heartbeat_controller.logger.isEnabledFor(logging.DEBUG)
        ):
            self.logger.debug("Sending: %s", _message_to_string(msg, data))

        if not force and self.stop.is_set():
            raise PyChromecastStopped("Socket client's thread is stopped.")
        if self.connecting or self._force_recon:
            raise NotConnected(f"Chromecast {self.host}:{self.port} is connecting...")

        # We have a socket
        assert self.socket is not None

        if callback_function and request_id is not None:
            self._request_callbacks[request_id] = callback_function
        try:
            self.socket.sendall(be_size + msg.SerializeToString())
        except OSError as exc:
            if request_id is not None:
                self._request_callbacks.pop(request_id, None)
            self._force_recon = True
            self.logger.warning("Error writing to socket: %s", exc)
            return False
        return True

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

    def register_connection_listener(
        self, listener: ConnectionStatusListener
    ) -> Callable[[], None]:
        """Register a connection listener for when the socket connection
        changes. Listeners will be called with
        listener.new_connection_status(status)

        Returns a function which unregisters the listener."""
        return self._connection_listeners.add(listener)

    def _ensure_channel_connected(self, destination_id: str) -> None:
        """Ensure we opened a channel to destination_id."""
        with self._socket_lock:
            if destination_id in self._open_channels:
                return
            # Added before sending, as the CONNECT itself goes to the channel
            self._open_channels.append(destination_id)

            try:
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
            except Exception:
                # Not sent, so it must be sent on the next connection
                self._open_channels.remove(destination_id)
                raise

    def disconnect_channel(self, destination_id: str) -> None:
        """Disconnect a channel with destination_id."""
        # Locked so a sender opening the channel can't remove it in between
        with self._socket_lock:
            if destination_id not in self._open_channels:
                return
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
                self.logger.exception("Exception")

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
