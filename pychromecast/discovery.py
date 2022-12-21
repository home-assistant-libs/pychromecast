"""Discovers Chromecasts on the network using mDNS/zeroconf."""
import abc
import functools
import itertools
import logging
import threading
import time
from uuid import UUID

import zeroconf

from .const import (
    CAST_TYPE_AUDIO,
    CAST_TYPE_GROUP,
    CAST_TYPES,
    MF_GOOGLE,
    SERVICE_TYPE_HOST,
    SERVICE_TYPE_MDNS,
)
from .dial import get_device_info, get_multizone_status, get_ssl_context
from .models import ZEROCONF_ERRORS, CastInfo, ServiceInfo

DISCOVER_TIMEOUT = 5

# Models matching this list will only be polled once by the HostBrowser
HOST_BROWSER_BLOCKED_MODEL_PREFIXES = [
    "HK",  # Harman Kardon speakers crash if polled: https://github.com/home-assistant/core/issues/52020
    "JBL",  # JBL speakers crash if polled: https://github.com/home-assistant/core/issues/52020
]

_LOGGER = logging.getLogger(__name__)


class AbstractCastListener(abc.ABC):
    """Listener for discovering chromecasts."""

    @abc.abstractmethod
    def add_cast(self, uuid, service):
        """A cast has been discovered.

        uuid: The cast's uuid, this is the dictionary key to find
        the chromecast metadata in CastBrowser.devices.
        service: First known MDNS service name or host:port
        """

    @abc.abstractmethod
    def remove_cast(self, uuid, service, cast_info):
        """A cast has been removed, meaning there are no longer any known services.

        uuid: The cast's uuid
        service: Last valid MDNS service name or host:port
        cast_info: CastInfo for the service to aid cleanup
        """

    @abc.abstractmethod
    def update_cast(self, uuid, service):
        """A cast has been updated.

        uuid: The cast's uuid
        service: MDNS service name or host:port
        """


def _is_blocked_from_host_browser(item, block_list, item_type):
    for blocked_prefix in block_list:
        if item.startswith(blocked_prefix):
            _LOGGER.debug("%s %s is blocked from host based polling", item_type, item)
            return True
    return False


def _is_model_blocked_from_host_browser(model):
    return _is_blocked_from_host_browser(
        model, HOST_BROWSER_BLOCKED_MODEL_PREFIXES, "Model"
    )


class SimpleCastListener(AbstractCastListener):
    """Helper for backwards compatibility."""

    def __init__(self, add_callback=None, remove_callback=None, update_callback=None):
        self._add_callback = add_callback
        self._remove_callback = remove_callback
        self._update_callback = update_callback

    def add_cast(self, uuid, service):
        if self._add_callback:
            self._add_callback(uuid, service)

    def remove_cast(self, uuid, service, cast_info):
        if self._remove_callback:
            self._remove_callback(uuid, service, cast_info)

    def update_cast(self, uuid, service):
        if self._update_callback:
            self._update_callback(uuid, service)


class ZeroConfListener:
    """Listener for ZeroConf service browser."""

    def __init__(self, cast_listener, devices, host_browser, lock):
        self._cast_listener = cast_listener
        self._devices = devices
        self._host_browser = host_browser
        self._services_lock = lock

    def remove_service(self, _zconf, typ, name):
        """Called by zeroconf when an mDNS service is lost."""
        _LOGGER.debug("remove_service %s, %s", typ, name)
        cast_info = None
        device_removed = False
        uuid = None
        service_info = ServiceInfo(SERVICE_TYPE_MDNS, name)
        # Lock because the HostBrowser may also add or remove items
        with self._services_lock:
            for uuid, info_for_uuid in self._devices.items():
                if service_info in info_for_uuid.services:
                    cast_info = info_for_uuid
                    info_for_uuid.services.remove(service_info)
                    if len(info_for_uuid.services) == 0:
                        device_removed = True
                    break

        if not cast_info:
            _LOGGER.debug("remove_service unknown %s, %s", typ, name)
            return

        if device_removed:
            self._cast_listener.remove_cast(uuid, name, cast_info)
        else:
            self._cast_listener.update_cast(uuid, name)

    def update_service(self, zconf, typ, name):
        """Called by zeroconf when an mDNS service is updated."""
        _LOGGER.debug("update_service %s, %s", typ, name)
        self._add_update_service(zconf, typ, name, self._cast_listener.update_cast)

    def add_service(self, zconf, typ, name):
        """Called by zeroconf when an mDNS service is discovered."""
        _LOGGER.debug("add_service %s, %s", typ, name)
        self._add_update_service(zconf, typ, name, self._cast_listener.add_cast)

    # pylint: disable-next=too-many-locals
    def _add_update_service(self, zconf, typ, name, callback):
        """Add or update a service."""
        service = None
        tries = 0
        if name.endswith("_sub._googlecast._tcp.local."):
            _LOGGER.debug("_add_update_service ignoring %s, %s", typ, name)
            return
        while service is None and tries < 4:
            try:
                service = zconf.get_service_info(typ, name)
            except ZEROCONF_ERRORS:
                # If the zeroconf fails to receive the necessary data we abort
                # adding the service
                # We do not catch zeroconf.NotRunningException as it's
                # an unrecoverable error.
                _LOGGER.debug(
                    "get_info_from_service failed to resolve service %s",
                    service,
                )
                break
            tries += 1

        if not service:
            _LOGGER.debug("_add_update_service failed to add %s, %s", typ, name)
            return

        def get_value(key):
            """Retrieve value and decode to UTF-8."""
            value = service.properties.get(key.encode("utf-8"))

            if value is None or isinstance(value, str):
                return value
            return value.decode("utf-8")

        addresses = service.parsed_addresses()
        host = addresses[0] if addresses else service.server

        # Store the host, in case mDNS stops working
        self._host_browser.add_hosts([host])

        friendly_name = get_value("fn")
        model_name = get_value("md")
        uuid = get_value("id")

        if not uuid:
            _LOGGER.debug(
                "_add_update_service failed to get uuid for %s, %s", typ, name
            )
            return

        # Ignore incorrect UUIDs from third-party Chromecast emulators
        try:
            uuid = UUID(uuid)
        except ValueError:
            _LOGGER.debug(
                "_add_update_service failed due to bad uuid for %s, %s, model %s",
                typ,
                name,
                model_name,
            )
            return

        service_info = ServiceInfo(SERVICE_TYPE_MDNS, name)

        # Lock because the HostBrowser may also add or remove items
        with self._services_lock:
            if service.port != 8009:
                cast_type = CAST_TYPE_GROUP
                manufacturer = MF_GOOGLE
            else:
                cast_type, manufacturer = CAST_TYPES.get(
                    model_name.lower(), (None, None)
                )
            if uuid not in self._devices:
                self._devices[uuid] = CastInfo(
                    {service_info},
                    uuid,
                    model_name,
                    friendly_name,
                    host,
                    service.port,
                    cast_type,
                    manufacturer,
                )
            else:
                # Update stored information
                services = self._devices[uuid].services
                services.add(service_info)
                self._devices[uuid] = CastInfo(
                    services,
                    uuid,
                    model_name,
                    friendly_name,
                    host,
                    service.port,
                    cast_type,
                    manufacturer,
                )

        callback(uuid, name)


class HostStatus:
    """Status of known host."""

    def __init__(self):
        self.failcount = 0
        self.no_polling = False


HOSTLISTENER_CYCLE_TIME = 30
HOSTLISTENER_MAX_FAIL = 5


class HostBrowser(threading.Thread):
    """Repeateadly poll a set of known hosts."""

    def __init__(self, cast_listener, devices, lock):
        super().__init__(daemon=True)
        self._cast_listener = cast_listener
        self._devices = devices
        self._known_hosts = {}
        self._next_update = time.time()
        self._services_lock = lock
        self._start_requested = False
        self._context = None
        self.stop = threading.Event()

    def add_hosts(self, known_hosts):
        """Add a list of known hosts to the set."""
        for host in known_hosts:
            if host not in self._known_hosts:
                _LOGGER.debug("Addded host %s", host)
                self._known_hosts[host] = HostStatus()

    def update_hosts(self, known_hosts):
        """Update the set of known hosts.

        Note: Removed hosts will no longer be polled, but services of any associated
        cast devices will not be purged.
        """
        if known_hosts is None:
            known_hosts = []

        self.add_hosts(known_hosts)

        for host in list(self._known_hosts.keys()):
            if host not in known_hosts:
                _LOGGER.debug("Removed host %s", host)
                self._known_hosts.pop(host)

    def run(self):
        """Start worker thread."""
        _LOGGER.debug("HostBrowser thread started")
        self._context = get_ssl_context()
        try:
            while not self.stop.is_set():
                self._poll_hosts()
                self._next_update += HOSTLISTENER_CYCLE_TIME
                self.stop.wait(max(self._next_update - time.time(), 0))
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unhandled exception in worker thread")
            raise
        _LOGGER.debug("HostBrowser thread done")

    def _poll_hosts(self):
        # Iterate over a copy because other threads may modify the known_hosts list
        known_hosts = list(self._known_hosts.keys())
        for host in known_hosts:
            devices = []
            uuids = []
            if self.stop.is_set():
                break
            try:
                hoststatus = self._known_hosts[host]
            except KeyError:
                # The host has been removed by another thread
                continue

            if hoststatus.no_polling:
                # This host should not be polled
                continue

            device_status = get_device_info(host, timeout=30, context=self._context)

            if not device_status:
                hoststatus.failcount += 1
                if hoststatus.failcount == HOSTLISTENER_MAX_FAIL:
                    self._update_devices(host, devices, uuids)
                hoststatus.failcount = min(
                    hoststatus.failcount, HOSTLISTENER_MAX_FAIL + 1
                )
                continue

            if (
                device_status.cast_type != CAST_TYPE_AUDIO
                or _is_model_blocked_from_host_browser(device_status.model_name)
            ):
                # Polling causes frame drops on some Android TVs,
                # https://github.com/home-assistant/core/issues/55435
                # Keep polling audio chromecasts to detect new speaker groups, but
                # exclude some devices which crash when polled
                # Note: This will not work well the IP is recycled to another cast
                # device.
                hoststatus.no_polling = True

            # We got device_status, try to get multizone status, then update devices
            hoststatus.failcount = 0
            devices.append(
                (
                    8009,
                    device_status.friendly_name,
                    device_status.model_name,
                    device_status.uuid,
                    device_status.cast_type,
                    device_status.manufacturer,
                )
            )
            uuids.append(device_status.uuid)

            multizone_status = (
                get_multizone_status(host, context=self._context)
                if device_status.multizone_supported
                else None
            )

            if multizone_status:
                for group in itertools.chain(
                    multizone_status.dynamic_groups, multizone_status.groups
                ):
                    # Note: This is currently (2021-02) not working for dynamic_groups, the
                    # ports of dynamic groups are not present in the eureka_info reply.
                    if group.host and group.host not in self._known_hosts:
                        self.add_hosts([group.host])
                    if group.port is None or group.host != host:
                        continue
                    devices.append(
                        (
                            group.port,
                            group.friendly_name,
                            "Google Cast Group",
                            group.uuid,
                            CAST_TYPE_GROUP,
                            "Google Inc.",
                        )
                    )
                    uuids.append(group.uuid)

            self._update_devices(host, devices, uuids)

    def _update_devices(self, host, devices, host_uuids):
        callbacks = []

        # Lock because the ZeroConfListener may also add or remove items
        with self._services_lock:
            for (
                port,
                friendly_name,
                model_name,
                uuid,
                cast_type,
                manufacturer,
            ) in devices:
                self._add_host_service(
                    host,
                    port,
                    friendly_name,
                    model_name,
                    uuid,
                    callbacks,
                    cast_type,
                    manufacturer,
                )

            for uuid in self._devices:
                for service in self._devices[uuid].services.copy():
                    if (
                        service.type == SERVICE_TYPE_HOST
                        and service.data[0] == host
                        and uuid not in host_uuids
                    ):
                        self._remove_host_service(host, uuid, callbacks)

        # Handle callbacks after releasing the lock
        for callback in callbacks:
            callback()

    def _add_host_service(
        self,
        host,
        port,
        friendly_name,
        model_name,
        uuid,
        callbacks,
        cast_type,
        manufacturer,
    ):
        service_info = ServiceInfo(SERVICE_TYPE_HOST, (host, port))

        callback = self._cast_listener.add_cast
        if uuid in self._devices:
            callback = self._cast_listener.update_cast
            cast_info = self._devices[uuid]
            if (
                service_info in cast_info.services
                and cast_info.model_name == model_name
                and cast_info.friendly_name == friendly_name
            ):
                # No changes, return
                return

        if uuid not in self._devices:
            self._devices[uuid] = CastInfo(
                {service_info},
                uuid,
                model_name,
                friendly_name,
                host,
                port,
                cast_type,
                manufacturer,
            )
        else:
            # Update stored information
            services = self._devices[uuid].services
            services.add(service_info)
            self._devices[uuid] = CastInfo(
                services,
                uuid,
                model_name,
                friendly_name,
                host,
                port,
                cast_type,
                manufacturer,
            )

        name = f"{host}:{port}"
        _LOGGER.debug(
            "Host %s (%s) up, adding or updating host based service", name, uuid
        )
        if callback:
            callbacks.append(functools.partial(callback, uuid, name))

    def _remove_host_service(self, host, uuid, callbacks):
        if uuid not in self._devices:
            return

        info_for_uuid = self._devices[uuid]
        for service in info_for_uuid.services:
            if service.type == SERVICE_TYPE_HOST and service.data[0] == host:
                info_for_uuid.services.remove(service)
                port = service.data[1]
                name = f"{host}:{port}"
                _LOGGER.debug(
                    "Host %s down or no longer handles uuid %s, removing host based service",
                    name,
                    uuid,
                )
                if len(info_for_uuid.services) == 0:
                    callbacks.append(
                        functools.partial(
                            self._cast_listener.remove_cast, uuid, name, info_for_uuid
                        )
                    )
                else:
                    callbacks.append(
                        functools.partial(self._cast_listener.update_cast, uuid, name)
                    )
                break


class CastBrowser:
    """Discover Chromecasts on the network.

    When a Chromecast is found, cast_listener.add_cast is called
    When a Chromecast is updated, cast_listener.update_cast is called
    When a Chromecast is lost, the cast_listener.remove_cast is called

    A shared zeroconf instance can be passed as zeroconf_instance. If no
    instance is passed, a new instance will be created.
    """

    def __init__(self, cast_listener, zeroconf_instance=None, known_hosts=None):
        self._cast_listener = cast_listener
        self.zc = zeroconf_instance  # pylint: disable=invalid-name
        self._zc_browser = None
        self.devices = {}
        self.services = self.devices  # For backwards compatibility
        self._services_lock = threading.Lock()
        self.host_browser = HostBrowser(
            self._cast_listener, self.devices, self._services_lock
        )
        self.zeroconf_listener = ZeroConfListener(
            self._cast_listener, self.devices, self.host_browser, self._services_lock
        )
        if known_hosts:
            self.host_browser.add_hosts(known_hosts)

    @property
    def count(self):
        """Number of discovered cast devices."""
        return len(self.devices)

    def set_zeroconf_instance(self, zeroconf_instance):
        """Set zeroconf_instance."""
        if self.zc:
            return
        self.zc = zeroconf_instance

    def start_discovery(self):
        """
        This method will start discovering chromecasts on separate threads. When
        a chromecast is discovered, callback will be called with the
        discovered chromecast's zeroconf name. This is the dictionary key to find
        the chromecast metadata in CastBrowser.devices.

        A shared zeroconf instance can be passed as zeroconf_instance. If no
        instance is passed, a new instance will be created.
        """

        if self.zc:
            self._zc_browser = zeroconf.ServiceBrowser(
                self.zc,
                "_googlecast._tcp.local.",
                self.zeroconf_listener,
            )
        self.host_browser.start()

    def stop_discovery(self):
        """Stop the chromecast discovery threads."""
        if self._zc_browser:
            try:
                self._zc_browser.cancel()
            except RuntimeError:
                # Throws if called from service callback when joining the zc browser thread
                pass
            self._zc_browser.zc.close()
        self.host_browser.stop.set()
        self.host_browser.join()


class CastListener(CastBrowser):
    """Backwards compatible helper class."""

    def __init__(self, add_callback=None, remove_callback=None, update_callback=None):
        _LOGGER.info("CastListener is deprecated, update to use CastBrowser instead")
        listener = SimpleCastListener(add_callback, remove_callback, update_callback)
        super().__init__(listener)


def start_discovery(cast_browser, zeroconf_instance):
    """Start discovering chromecasts on the network."""
    _LOGGER.info(
        "start_discovery is deprecated, call cast_browser.start_discovery() instead"
    )
    cast_browser.set_zeroconf_instance(zeroconf_instance)
    cast_browser.start_discovery()
    return cast_browser


def stop_discovery(cast_browser):
    """Stop the chromecast discovery threads."""
    _LOGGER.info(
        "stop_discovery is deprecated, call cast_browser.stop_discovery() instead"
    )
    cast_browser.stop_discovery()


def discover_chromecasts(
    max_devices=None, timeout=DISCOVER_TIMEOUT, zeroconf_instance=None, known_hosts=None
):
    """
    Discover chromecasts on the network.

    Returns a tuple of:
      A list of chromecast devices, or an empty list if no matching chromecasts were
      found.
      A service browser to keep the Chromecast mDNS data updated. When updates
      are (no longer) needed, call browser.stop_discovery().

    :param zeroconf_instance: An existing zeroconf instance.
    """

    def add_callback(_uuid, _service):
        """Called when zeroconf has discovered a new chromecast."""
        if max_devices is not None and browser.count >= max_devices:
            discover_complete.set()

    discover_complete = threading.Event()
    zconf = zeroconf_instance or zeroconf.Zeroconf()
    browser = CastBrowser(SimpleCastListener(add_callback), zconf, known_hosts)
    browser.start_discovery()

    # Wait for the timeout or the maximum number of devices
    discover_complete.wait(timeout)

    return (list(browser.devices.values()), browser)


def discover_listed_chromecasts(
    friendly_names=None,
    uuids=None,
    discovery_timeout=DISCOVER_TIMEOUT,
    zeroconf_instance=None,
    known_hosts=None,
):
    """
    Searches the network for chromecast devices matching a list of friendly
    names or a list of UUIDs.

    Returns a tuple of:
      A list of chromecast devices matching the criteria,
      or an empty list if no matching chromecasts were found.
      A service browser to keep the Chromecast mDNS data updated. When updates
      are (no longer) needed, call browser.stop_discovery().

    :param friendly_names: A list of wanted friendly names
    :param uuids: A list of wanted uuids
    :param discovery_timeout: A floating point number specifying the time to wait
                               devices matching the criteria have been found.
    :param zeroconf_instance: An existing zeroconf instance.
    """

    cc_list = {}

    def add_callback(uuid, service):
        _LOGGER.debug("Got cast %s, %s", uuid, service)
        service = browser.devices[uuid]
        friendly_name = service[3]
        if uuids and uuid in uuids:
            cc_list[uuid] = browser.devices[uuid]
            uuids.remove(uuid)
        if friendly_names and friendly_name in friendly_names:
            cc_list[uuid] = browser.devices[uuid]
            friendly_names.remove(friendly_name)
        if not friendly_names and not uuids:
            discover_complete.set()

    discover_complete = threading.Event()

    zconf = zeroconf_instance or zeroconf.Zeroconf()
    browser = CastBrowser(SimpleCastListener(add_callback), zconf, known_hosts)
    browser.start_discovery()

    # Wait for the timeout or found all wanted devices
    discover_complete.wait(discovery_timeout)
    return (list(cc_list.values()), browser)
