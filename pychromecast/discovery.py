"""Discovers Chromecasts on the network using mDNS/zeroconf."""

from __future__ import annotations

import abc
from collections.abc import Callable
import functools
import itertools
import logging
import ssl
import threading
import time
from uuid import UUID

import zeroconf

from .const import CAST_TYPE_AUDIO, CAST_TYPE_GROUP, CAST_TYPES, MF_GOOGLE
from .dial import get_device_info, get_multizone_status, get_ssl_context
from .models import ZEROCONF_ERRORS, CastInfo, HostServiceInfo, MDNSServiceInfo

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
    def add_cast(self, uuid: UUID, service: str) -> None:
        """A cast has been discovered.

        uuid: The cast's uuid, this is the dictionary key to find
        the chromecast metadata in CastBrowser.devices.
        service: First known MDNS service name or host:port
        """

    @abc.abstractmethod
    def remove_cast(self, uuid: UUID, service: str, cast_info: CastInfo) -> None:
        """A cast has been removed, meaning there are no longer any known services.

        uuid: The cast's uuid
        service: Last valid MDNS service name or host:port
        cast_info: CastInfo for the service to aid cleanup
        """

    @abc.abstractmethod
    def update_cast(self, uuid: UUID, service: str) -> None:
        """A cast has been updated.

        uuid: The cast's uuid
        service: MDNS service name or host:port
        """


def _is_blocked_from_host_browser(
    item: str, block_list: list[str], item_type: str
) -> bool:
    for blocked_prefix in block_list:
        if item.startswith(blocked_prefix):
            _LOGGER.debug("%s %s is blocked from host based polling", item_type, item)
            return True
    return False


def _is_model_blocked_from_host_browser(model: str) -> bool:
    return _is_blocked_from_host_browser(
        model, HOST_BROWSER_BLOCKED_MODEL_PREFIXES, "Model"
    )


class SimpleCastListener(AbstractCastListener):
    """Helper for backwards compatibility."""

    def __init__(
        self,
        add_callback: Callable[[UUID, str], None] | None = None,
        remove_callback: Callable[[UUID, str, CastInfo], None] | None = None,
        update_callback: Callable[[UUID, str], None] | None = None,
    ):
        self._add_callback = add_callback
        self._remove_callback = remove_callback
        self._update_callback = update_callback

    def add_cast(self, uuid: UUID, service: str) -> None:
        if self._add_callback:
            self._add_callback(uuid, service)

    def remove_cast(self, uuid: UUID, service: str, cast_info: CastInfo) -> None:
        if self._remove_callback:
            self._remove_callback(uuid, service, cast_info)

    def update_cast(self, uuid: UUID, service: str) -> None:
        if self._update_callback:
            self._update_callback(uuid, service)


class ZeroConfListener(zeroconf.ServiceListener):
    """Listener for ZeroConf service browser."""

    def __init__(
        self,
        cast_listener: AbstractCastListener,
        devices: dict[UUID, CastInfo],
        host_browser: HostBrowser,
        lock: threading.Lock,
    ) -> None:
        self._cast_listener = cast_listener
        self._devices = devices
        self._host_browser = host_browser
        self._services_lock = lock

    def remove_service(self, zc: zeroconf.Zeroconf, type_: str, name: str) -> None:
        """Called by zeroconf when an mDNS service is lost."""
        _LOGGER.debug("remove_service %s, %s", type_, name)
        cast_info = None
        device_removed = False
        uuid = None
        service_info = MDNSServiceInfo(name)
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
            _LOGGER.debug("remove_service unknown %s, %s", type_, name)
            return

        if device_removed:
            self._cast_listener.remove_cast(uuid, name, cast_info)
        else:
            self._cast_listener.update_cast(uuid, name)

    def update_service(self, zc: zeroconf.Zeroconf, type_: str, name: str) -> None:
        """Called by zeroconf when an mDNS service is updated."""
        _LOGGER.debug("update_service %s, %s", type_, name)
        self._add_update_service(zc, type_, name, self._cast_listener.update_cast)

    def add_service(self, zc: zeroconf.Zeroconf, type_: str, name: str) -> None:
        """Called by zeroconf when an mDNS service is discovered."""
        _LOGGER.debug("add_service %s, %s", type_, name)
        self._add_update_service(zc, type_, name, self._cast_listener.add_cast)

    # pylint: disable-next=too-many-locals
    def _add_update_service(
        self,
        zconf: zeroconf.Zeroconf,
        typ: str,
        name: str,
        callback: Callable[[UUID, str], None],
    ) -> None:
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

        if service.port is None:
            _LOGGER.debug("_add_update_service port is None")
            return

        def get_value(key: str) -> str | None:
            """Retrieve value and decode to UTF-8."""
            value = service.properties.get(key.encode("utf-8"))

            # zeroconf would keep str version of cached items, this check
            # can be removed if we pin zeroconf to a version where this is
            # removed.
            if value is None or isinstance(value, str):  # type: ignore[unreachable]
                return value
            return value.decode("utf-8")

        addresses = service.parsed_addresses()
        host = addresses[0] if addresses else service.server

        if host is None:
            _LOGGER.debug(
                "_add_update_service failed to get host for %s, %s", typ, name
            )
            return

        # Store the host, in case mDNS stops working
        self._host_browser.add_hosts([host])

        friendly_name = get_value("fn")
        model_name = get_value("md") or "Unknown model name"
        uuid_str = get_value("id")

        if not uuid_str:
            _LOGGER.debug(
                "_add_update_service failed to get uuid for %s, %s", typ, name
            )
            return

        # Ignore incorrect UUIDs from third-party Chromecast emulators
        try:
            uuid = UUID(uuid_str)
        except ValueError:
            _LOGGER.debug(
                "_add_update_service failed due to bad uuid for %s, %s, model %s",
                typ,
                name,
                model_name,
            )
            return

        service_info = MDNSServiceInfo(name)

        # Lock because the HostBrowser may also add or remove items
        with self._services_lock:
            cast_type: str | None
            manufacturer: str | None
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

    def __init__(self) -> None:
        self.failcount = 0
        self.no_polling = False


HOSTLISTENER_CYCLE_TIME = 30
HOSTLISTENER_MAX_FAIL = 5


class HostBrowser(threading.Thread):
    """Repeateadly poll a set of known hosts."""

    def __init__(
        self,
        cast_listener: AbstractCastListener,
        devices: dict[UUID, CastInfo],
        lock: threading.Lock,
    ) -> None:
        super().__init__(daemon=True)
        self._cast_listener = cast_listener
        self._devices = devices
        self._known_hosts: dict[str, HostStatus] = {}
        self._next_update = time.time()
        self._services_lock = lock
        self._start_requested = False
        self._context: ssl.SSLContext | None = None
        self.stop = threading.Event()

    def add_hosts(self, known_hosts: list[str]) -> None:
        """Add a list of known hosts to the set."""
        for host in known_hosts:
            if host not in self._known_hosts:
                _LOGGER.debug("Addded host %s", host)
                self._known_hosts[host] = HostStatus()

    def update_hosts(self, known_hosts: list[str] | None) -> None:
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

    def run(self) -> None:
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

    def _poll_hosts(self) -> None:
        # Iterate over a copy because other threads may modify the known_hosts list
        known_hosts = list(self._known_hosts.keys())
        for host in known_hosts:
            devices: list[tuple[int, str, str, UUID, str, str]] = []
            uuids: list[UUID] = []
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
                    # We can't contact the host, drop all its devices and UUIDs
                    self._update_devices(host, devices, uuids)
                hoststatus.failcount = min(
                    hoststatus.failcount, HOSTLISTENER_MAX_FAIL + 1
                )
                continue

            if not device_status.uuid:
                _LOGGER.debug("host %s does not report UUID", host)
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
                    if group.port is None or group.uuid is None or group.host != host:
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

    def _update_devices(
        self,
        host: str,
        devices: list[tuple[int, str, str, UUID, str, str]],
        host_uuids: list[UUID],
    ) -> None:
        callbacks: list[Callable[[], None]] = []

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
                        isinstance(service, HostServiceInfo)
                        and service.host == host
                        and uuid not in host_uuids
                    ):
                        self._remove_host_service(host, uuid, callbacks)

        # Handle callbacks after releasing the lock
        for callback in callbacks:
            callback()

    def _add_host_service(
        self,
        host: str,
        port: int,
        friendly_name: str,
        model_name: str,
        uuid: UUID,
        callbacks: list[Callable[[], None]],
        cast_type: str,
        manufacturer: str,
    ) -> None:
        service_info = HostServiceInfo(host, port)

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
        callbacks.append(functools.partial(callback, uuid, name))

    def _remove_host_service(
        self,
        host: str,
        uuid: UUID,
        callbacks: list[Callable[[], None]],
    ) -> None:
        if uuid not in self._devices:
            return

        info_for_uuid = self._devices[uuid]
        for service in info_for_uuid.services:
            if isinstance(service, HostServiceInfo) and service.host == host:
                info_for_uuid.services.remove(service)
                port = service.port
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

    def __init__(
        self,
        cast_listener: AbstractCastListener,
        zeroconf_instance: zeroconf.Zeroconf | None = None,
        known_hosts: list[str] | None = None,
    ) -> None:
        self._cast_listener = cast_listener
        self.zc = zeroconf_instance  # pylint: disable=invalid-name
        self._zc_browser: zeroconf.ServiceBrowser | None = None
        self.devices: dict[UUID, CastInfo] = {}
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
    def count(self) -> int:
        """Number of discovered cast devices."""
        return len(self.devices)

    def set_zeroconf_instance(self, zeroconf_instance: zeroconf.Zeroconf) -> None:
        """Set zeroconf_instance."""
        if self.zc:
            return
        self.zc = zeroconf_instance

    def start_discovery(self) -> None:
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

    def stop_discovery(self) -> None:
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
    """Backwards compatible helper class.

    Deprecated as of February 2021, will be removed in June 2024.
    """

    def __init__(
        self,
        add_callback: Callable[[UUID, str], None] | None = None,
        remove_callback: Callable[[UUID, str, CastInfo], None] | None = None,
        update_callback: Callable[[UUID, str], None] | None = None,
    ):
        _LOGGER.info(
            "CastListener is deprecated and will be removed in June 2024, update to use CastBrowser instead"
        )
        listener = SimpleCastListener(add_callback, remove_callback, update_callback)
        super().__init__(listener)


def start_discovery(
    cast_browser: CastBrowser, zeroconf_instance: zeroconf.Zeroconf
) -> CastBrowser:
    """Start discovering chromecasts on the network.

    Deprecated as of February 2021, will be removed in June 2024.
    """
    _LOGGER.info(
        "start_discovery is deprecated and will be removed in June 2024, call CastBrowser.start_discovery() instead"
    )
    cast_browser.set_zeroconf_instance(zeroconf_instance)
    cast_browser.start_discovery()
    return cast_browser


def stop_discovery(cast_browser: CastBrowser) -> None:
    """Stop the chromecast discovery threads.

    Deprecated as of February 2021, will be removed in June 2024.
    """
    _LOGGER.info(
        "stop_discovery is deprecated and will be removed in June 2024, call CastBrowser.stop_discovery() instead"
    )
    cast_browser.stop_discovery()


def discover_chromecasts(
    max_devices: int | None = None,
    timeout: float = DISCOVER_TIMEOUT,
    zeroconf_instance: zeroconf.Zeroconf | None = None,
    known_hosts: list[str] | None = None,
) -> tuple[list[CastInfo], CastBrowser]:
    """
    Discover chromecasts on the network.

    Deprecated as of February 2021, will be removed in June 2024.


    Returns a tuple of:
      A list of chromecast devices, or an empty list if no chromecasts were found.
      A service browser to keep the Chromecast mDNS data updated. When updates
      are (no longer) needed, call browser.stop_discovery().

    :param zeroconf_instance: An existing zeroconf instance.
    """

    _LOGGER.info(
        "discover_chromecasts is deprecated and will be removed in June 2024, update to use CastBrowser instead."
    )

    def add_callback(_uuid: UUID, _service: str) -> None:
        """Called when a new chromecast has been discovered."""
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
    friendly_names: list[str] | None = None,
    uuids: list[UUID] | None = None,
    discovery_timeout: float = DISCOVER_TIMEOUT,
    zeroconf_instance: zeroconf.Zeroconf | None = None,
    known_hosts: list[str] | None = None,
) -> tuple[list[CastInfo], CastBrowser]:
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

    cc_list: dict[UUID, CastInfo] = {}

    def add_callback(uuid: UUID, service: str) -> None:
        _LOGGER.debug("Got cast %s, %s", uuid, service)
        cast_info = browser.devices[uuid]
        friendly_name = cast_info.friendly_name
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
