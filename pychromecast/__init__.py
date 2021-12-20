"""
PyChromecast: remote control your Chromecast
"""
import logging
import fnmatch
from threading import Event

import threading

import zeroconf

from .config import *  # noqa: F403
from .error import *  # noqa: F403
from . import socket_client
from .discovery import (  # noqa: F401
    DISCOVER_TIMEOUT,
    CastBrowser,
    CastListener,  # Deprecated
    ServiceInfo,
    SimpleCastListener,
    discover_chromecasts,
    start_discovery,
    stop_discovery,
)
from .dial import get_cast_type
from .const import CAST_TYPE_CHROMECAST, SERVICE_TYPE_HOST
from .controllers.media import STREAM_TYPE_BUFFERED  # noqa: F401
from .models import CastInfo

__all__ = ("__version__", "__version_info__", "get_chromecasts", "Chromecast")
__version_info__ = ("0", "7", "6")
__version__ = ".".join(__version_info__)

IDLE_APP_ID = "E8C28D3C"
IGNORE_CEC = []

_LOGGER = logging.getLogger(__name__)


def get_chromecast_from_host(host, tries=None, retry_wait=None, timeout=None):
    """Creates a Chromecast object from a zeroconf host."""
    # Build device status from the mDNS info, this information is
    # the primary source and the remaining will be fetched
    # later on.
    ip_address, port, uuid, model_name, friendly_name = host
    _LOGGER.debug("get_chromecast_from_host %s", host)
    port = port or 8009
    services = [ServiceInfo(SERVICE_TYPE_HOST, (ip_address, port))]
    cast_info = CastInfo(
        services, uuid, model_name, friendly_name, ip_address, port, None, None
    )
    return Chromecast(
        cast_info=cast_info,
        tries=tries,
        timeout=timeout,
        retry_wait=retry_wait,
    )


# Alias for backwards compatibility
_get_chromecast_from_host = get_chromecast_from_host  # pylint: disable=invalid-name


def get_chromecast_from_cast_info(
    cast_info, zconf, tries=None, retry_wait=None, timeout=None
):
    """Creates a Chromecast object from a zeroconf service."""
    _LOGGER.debug("get_chromecast_from_cast_info %s", cast_info)
    return Chromecast(
        cast_info=cast_info,
        tries=tries,
        timeout=timeout,
        retry_wait=retry_wait,
        zconf=zconf,
    )


# Alias for backwards compatibility
_get_chromecast_from_service = (  # pylint: disable=invalid-name
    get_chromecast_from_cast_info
)


def get_listed_chromecasts(
    friendly_names=None,
    uuids=None,
    tries=None,
    retry_wait=None,
    timeout=None,
    discovery_timeout=DISCOVER_TIMEOUT,
    zeroconf_instance=None,
    known_hosts=None,
):
    """
    Searches the network for chromecast devices matching a list of friendly
    names or a list of UUIDs.

    Returns a tuple of:
      A list of Chromecast objects matching the criteria,
      or an empty list if no matching chromecasts were found.
      A service browser to keep the Chromecast mDNS data updated. When updates
      are (no longer) needed, call browser.stop_discovery().

    To only discover chromecast devices without connecting to them, use
    discover_listed_chromecasts instead.

    :param friendly_names: A list of wanted friendly names
    :param uuids: A list of wanted uuids
    :param tries: passed to get_chromecasts
    :param retry_wait: passed to get_chromecasts
    :param timeout: passed to get_chromecasts
    :param discovery_timeout: A floating point number specifying the time to wait
                               devices matching the criteria have been found.
    :param zeroconf_instance: An existing zeroconf instance.
    """

    cc_list = {}

    def add_callback(uuid, _service):
        _LOGGER.debug(
            "Found chromecast %s (%s)", browser.devices[uuid].friendly_name, uuid
        )

        def get_chromecast_from_uuid(uuid):
            return get_chromecast_from_cast_info(
                browser.devices[uuid],
                zconf=zconf,
                tries=tries,
                retry_wait=retry_wait,
                timeout=timeout,
            )

        friendly_name = browser.devices[uuid].friendly_name
        try:
            if uuids and uuid in uuids:
                if uuid not in cc_list:
                    cc_list[uuid] = get_chromecast_from_uuid(uuid)
                uuids.remove(uuid)
            if friendly_names and friendly_name in friendly_names:
                if uuid not in cc_list:
                    cc_list[uuid] = get_chromecast_from_uuid(uuid)
                friendly_names.remove(friendly_name)
            if not friendly_names and not uuids:
                discover_complete.set()
        except ChromecastConnectionError:  # noqa: F405
            pass

    discover_complete = Event()

    zconf = zeroconf_instance or zeroconf.Zeroconf()
    browser = CastBrowser(SimpleCastListener(add_callback), zconf, known_hosts)
    browser.start_discovery()

    # Wait for the timeout or found all wanted devices
    discover_complete.wait(discovery_timeout)
    return (list(cc_list.values()), browser)


def get_chromecasts(  # pylint: disable=too-many-locals
    tries=None,
    retry_wait=None,
    timeout=None,
    blocking=True,
    callback=None,
    zeroconf_instance=None,
    known_hosts=None,
):
    """
    Searches the network for chromecast devices and creates a Chromecast object
    for each discovered device.

    Returns a tuple of:
      A list of Chromecast objects, or an empty list if no matching chromecasts were
      found.
      A service browser to keep the Chromecast mDNS data updated. When updates
      are (no longer) needed, call browser.stop_discovery().

    To only discover chromecast devices without connecting to them, use
    discover_chromecasts instead.

    Parameters tries, timeout, retry_wait and blocking_app_launch controls the
    behavior of the created Chromecast instances.

    :param tries: Number of retries to perform if the connection fails.
                  None for infinite retries.
    :param timeout: A floating point number specifying the socket timeout in
                    seconds. None means to use the default which is 30 seconds.
    :param retry_wait: A floating point number specifying how many seconds to
                       wait between each retry. None means to use the default
                       which is 5 seconds.
    :param blocking: If True, returns a list of discovered chromecast devices.
                     If False, triggers a callback for each discovered chromecast,
                     and returns a function which can be executed to stop discovery.
    :param callback: Callback which is triggered for each discovered chromecast when
                     blocking = False.
    :param zeroconf_instance: An existing zeroconf instance.
    """
    if blocking:
        # Thread blocking chromecast discovery
        devices, browser = discover_chromecasts(known_hosts=known_hosts)
        cc_list = []
        for device in devices:
            try:
                cc_list.append(
                    get_chromecast_from_cast_info(
                        device,
                        browser.zc,
                        tries=tries,
                        retry_wait=retry_wait,
                        timeout=timeout,
                    )
                )
            except ChromecastConnectionError:  # noqa: F405
                pass
        return (cc_list, browser)

    # Callback based chromecast discovery
    if not callable(callback):
        raise ValueError("Nonblocking discovery requires a callback function.")

    known_uuids = set()

    def add_callback(uuid, _service):
        """Called when zeroconf has discovered a new chromecast."""
        if uuid in known_uuids:
            return
        try:
            callback(
                get_chromecast_from_cast_info(
                    browser.devices[uuid],
                    zconf=zconf,
                    tries=tries,
                    retry_wait=retry_wait,
                    timeout=timeout,
                )
            )
            known_uuids.add(uuid)
        except ChromecastConnectionError:  # noqa: F405
            pass

    zconf = zeroconf_instance or zeroconf.Zeroconf()
    browser = CastBrowser(SimpleCastListener(add_callback), zconf, known_hosts)
    browser.start_discovery()
    return browser


# pylint: disable=too-many-instance-attributes, too-many-public-methods
class Chromecast:
    """
    Class to interface with a ChromeCast.

    :param cast_info: CastInfo with information for the device.
    :param tries: Number of retries to perform if the connection fails.
                  None for infinite retries.
    :param timeout: A floating point number specifying the socket timeout in
                    seconds. None means to use the default which is 30 seconds.
    :param retry_wait: A floating point number specifying how many seconds to
                       wait between each retry. None means to use the default
                       which is 5 seconds.
    :param zconf: A zeroconf instance, needed if a the services if cast info includes
                  mDNS services.
                  The zeroconf instance may be obtained from the browser returned by
                  pychromecast.start_discovery().
    """

    def __init__(
        self, cast_info, *, tries=None, timeout=None, retry_wait=None, zconf=None
    ):
        self.logger = logging.getLogger(__name__)

        if not cast_info.cast_type:
            cast_info = get_cast_type(cast_info, zconf)
        self.cast_info = cast_info

        self.status = None
        self.status_event = threading.Event()

        self.socket_client = socket_client.SocketClient(
            cast_type=cast_info.cast_type,
            tries=tries,
            timeout=timeout,
            retry_wait=retry_wait,
            services=cast_info.services,
            zconf=zconf,
        )

        receiver_controller = self.socket_client.receiver_controller
        receiver_controller.register_status_listener(self)

        # Forward these methods
        self.set_volume = receiver_controller.set_volume
        self.set_volume_muted = receiver_controller.set_volume_muted
        self.play_media = self.socket_client.media_controller.play_media
        self.register_handler = self.socket_client.register_handler
        self.unregister_handler = self.socket_client.unregister_handler
        self.register_status_listener = receiver_controller.register_status_listener
        self.register_launch_error_listener = (
            receiver_controller.register_launch_error_listener
        )
        self.register_connection_listener = (
            self.socket_client.register_connection_listener
        )

    @property
    def ignore_cec(self):
        """Returns whether the CEC data should be ignored."""
        return self.cast_info.friendly_name is not None and any(
            fnmatch.fnmatchcase(self.cast_info.friendly_name, pattern)
            for pattern in IGNORE_CEC
        )

    @property
    def is_idle(self):
        """Returns if there is currently an app running."""
        return (
            self.status is None
            or self.app_id in (None, IDLE_APP_ID)
            or (
                self.cast_type == CAST_TYPE_CHROMECAST
                and not self.status.is_active_input
                and not self.ignore_cec
            )
        )

    @property
    def uuid(self):
        """Returns the unique UUID of the Chromecast device."""
        return self.cast_info.uuid

    @property
    def name(self):
        """
        Returns the friendly name set for the Chromecast device.
        This is the name that the end-user chooses for the cast device.
        """
        return self.cast_info.friendly_name

    @property
    def uri(self):
        """Returns the device URI (ip:port)"""
        return f"{self.socket_client.host}:{self.socket_client.port}"

    @property
    def model_name(self):
        """Returns the model name of the Chromecast device."""
        return self.cast_info.model_name

    @property
    def cast_type(self):
        """
        Returns the type of the Chromecast device.
        This is one of CAST_TYPE_CHROMECAST for regular Chromecast device,
        CAST_TYPE_AUDIO for Chromecast devices that only support audio
        and CAST_TYPE_GROUP for virtual a Chromecast device that groups
        together two or more cast (Audio for now) devices.

        :rtype: str
        """
        return self.cast_info.cast_type

    @property
    def app_id(self):
        """Returns the current app_id."""
        return self.status.app_id if self.status else None

    @property
    def app_display_name(self):
        """Returns the name of the current running app."""
        return self.status.display_name if self.status else None

    @property
    def media_controller(self):
        """Returns the media controller."""
        return self.socket_client.media_controller

    def new_cast_status(self, status):
        """Called when a new status received from the Chromecast."""
        self.status = status
        if status:
            self.status_event.set()

    def start_app(self, app_id, force_launch=False):
        """Start an app on the Chromecast."""
        self.logger.info("Starting app %s", app_id)

        self.socket_client.receiver_controller.launch_app(app_id, force_launch)

    def quit_app(self):
        """Tells the Chromecast to quit current app_id."""
        self.logger.info("Quiting current app")

        self.socket_client.receiver_controller.stop_app()

    def volume_up(self, delta=0.1):
        """Increment volume by 0.1 (or delta) unless it is already maxed.
        Returns the new volume.

        """
        if delta <= 0:
            raise ValueError(f"volume delta must be greater than zero, not {delta}")
        return self.set_volume(self.status.volume_level + delta)

    def volume_down(self, delta=0.1):
        """Decrement the volume by 0.1 (or delta) unless it is already 0.
        Returns the new volume.
        """
        if delta <= 0:
            raise ValueError(f"volume delta must be greater than zero, not {delta}")
        return self.set_volume(self.status.volume_level - delta)

    def wait(self, timeout=None):
        """
        Waits until the cast device is ready for communication. The device
        is ready as soon a status message has been received.

        If the worker thread is not already running, it will be started.

        If the status has already been received then the method returns
        immediately.

        :param timeout: a floating point number specifying a timeout for the
                        operation in seconds (or fractions thereof). Or None
                        to block forever.
        """
        if not self.socket_client.is_alive():
            self.socket_client.start()
        self.status_event.wait(timeout=timeout)

    def connect(self):
        """Connect to the chromecast.

        Must only be called if the worker thread will not be started.
        """
        self.socket_client.connect()

    def disconnect(self, timeout=None, blocking=True):
        """
        Disconnects the chromecast and waits for it to terminate.

        :param timeout: a floating point number specifying a timeout for the
                        operation in seconds (or fractions thereof). Or None
                        to block forever.
        :param blocking: If True it will block until the disconnection is
                         complete, otherwise it will return immediately.
        """
        self.socket_client.disconnect()
        if blocking:
            self.join(timeout=timeout)

    def join(self, timeout=None):
        """
        Blocks the thread of the caller until the chromecast connection is
        stopped.

        :param timeout: a floating point number specifying a timeout for the
                        operation in seconds (or fractions thereof). Or None
                        to block forever.
        """
        self.socket_client.join(timeout=timeout)

    def start(self):
        """
        Start the chromecast connection's worker thread.
        """
        self.socket_client.start()

    def __del__(self):
        try:
            self.socket_client.stop.set()
        except AttributeError:
            pass

    def __repr__(self):
        return (
            f"Chromecast({self.socket_client.host!r}, port={self.socket_client.port!r}, "
            f"cast_info={self.cast_info!r})"
        )

    def __unicode__(self):
        return (
            f"Chromecast({self.socket_client.host}, {self.socket_client.port}, "
            f"{self.cast_info.friendly_name}, {self.cast_info.model_name}, "
            f"{self.cast_info.manufacturer})"
        )
